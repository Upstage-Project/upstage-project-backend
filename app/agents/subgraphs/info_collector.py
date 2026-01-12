# app/agents/subgraphs/info_collector.py
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.state import InfoCollectorAgentState
from app.agents.tools import (
    resolve_ticker,
    search_news,
    extract_urls_from_search_result,
    fetch_article_from_url,
    get_financial_statement,
    add_many_to_invest_kb,
)
from app.core.logger import log_agent_step


# =========================================================
# 0) 간단 휴리스틱(Heuristic) + 유틸 함수들
# ---------------------------------------------------------
# 이 파일은 "투자 정보 수집 서브그래프"로,
# 사용자 질문 → 회사 식별 → 뉴스 검색 → 기사 본문 수집 → (필요 시) 재무정보 조회
# → 수집한 텍스트를 KB(지식베이스)에 저장하는 흐름을 자동으로 돌린다.
#
# 여기(0번 섹션)는 그 흐름에서 "판단에 필요한 간단한 규칙"과
# ToolNode에 전달할 tool_call 포맷을 만들어주는 유틸들을 모아둔 영역이다.
# =========================================================

# 재무 관련 질문인지 빠르게 감지하기 위한 키워드 목록
# (완벽한 분류기가 아니라 '대충 감지하는' 휴리스틱이다)
FIN_KEYWORDS = ["실적", "매출", "영업이익", "순이익", "재무", "재무제표", "손익", "자산", "부채", "자본", "ROE", "PER", "PBR"]

def _wants_financials(user_query: str) -> bool:
    """
    사용자의 질문이 '재무/실적/재무제표'를 요구하는지 여부를
    간단 키워드 매칭으로 판단한다.

    - True이면: 뒤 단계에서 get_financial_statement(DART 등)까지 호출
    - False이면: 뉴스/기사 수집까지만 하고 재무 조회는 생략
    """
    q = (user_query or "").lower()
    return any(k.lower() in q for k in FIN_KEYWORDS)

def _default_bsns_year() -> int:
    """
    재무조회 기본 연도(bsns_year)를 정한다.
    - 1월 초에는 당해년도 재무가 아직 확정/공시 전일 가능성이 높으므로
      기본적으로 '전년도'를 먼저 시도한다.
    """
    return datetime.now().year - 1

def _tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph의 ToolNode가 인식할 수 있는 tool_call 포맷을 만들어준다.

    tool_calls=[{"name": "...", "args": {...}, "id": "..."}]
    - id는 tool call을 추적하기 위한 고유값(uuid)
    """
    return {"name": name, "args": args, "id": str(uuid.uuid4())}

def _get_user_query(messages: List[Any]) -> str:
    """
    state.messages에서 가장 마지막 HumanMessage(사용자 발화)를 찾아서
    그 내용을 '현재 사용자 질문'으로 사용한다.

    - planner가 다음 행동을 결정할 때 "사용자 질문 텍스트"가 필요함
    """
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return ""


# =========================================================
# 1) Planner 노드: "다음에 호출할 tool 1개"를 결정한다
# ---------------------------------------------------------
# 이 서브그래프의 핵심은 plan_next_action()이다.
# - 현재까지 collected에 쌓인 상태(회사 식별됐는지, 뉴스 가져왔는지 등)를 보고
# - 다음 단계에서 실행할 Tool을 1개만 골라서
# - AIMessage(tool_calls=[...]) 형태로 반환한다.
#
# 즉,
#   plan_next_action -> tools(ToolNode) -> accumulate -> plan_next_action ...
# 를 반복하면서 단계별 수집을 진행한다.
#
# (중요) 여기서 LLM이 "자유롭게 계획을 쓰는" 방식이 아니라
# 코드 if/else로 다음 tool을 결정하는 "결정적(deterministic) planner"다.
# =========================================================
def plan_next_action(state: InfoCollectorAgentState):
    """
    현재 state를 보고 다음 tool call을 1개 결정하는 함수.

    state 구조(대략):
    - state["messages"]: LangChain 메시지들(Human/AI/ToolMessage) 누적
    - state["collected"]: 수집 진행 상황(phase), 중간 결과(news, urls, articles, financials 등)

    반환:
    - {"collected": updated_collected, "messages": [AIMessage(...)]}
      (AIMessage에 tool_calls가 있으면 다음 노드 tools로 라우팅됨)
    """
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    # ---- 진행 상태용 키들 초기화 ----
    # 여러 번 loop를 돌기 때문에, 최초 1회만 기본값을 세팅
    collected.setdefault("phase", "start")
    collected.setdefault("fetch_article_index", 0)  # urls 중 몇 번째 기사를 fetch할지 인덱스
    collected.setdefault("kb_save_queue", [])       # KB에 저장할 문서(텍스트+메타데이터) 임시 큐
    collected.setdefault("kb_saved", [])            # KB 저장 결과 기록(성공/실패 로그)
    collected.setdefault("news", None)              # search_news에서 뽑은 items 리스트
    collected.setdefault("news_raw", None)          # search_news 원본 dict
    collected.setdefault("urls", None)              # 검색 결과에서 추출한 URL 리스트
    collected.setdefault("articles", [])            # fetch한 기사 본문 dict 리스트
    collected.setdefault("financials", None)        # 재무조회 결과 dict
    collected.setdefault("errors", [])              # 도구 실패/예외 결과 저장
    collected.setdefault("loop_count", 0)           # 안전장치용 loop 카운트

    # ---- 무한 루프 방지 안전장치 ----
    collected["loop_count"] += 1
    if collected["loop_count"] > 20:
        # 20번 이상 도는 경우 종료시켜서 runaway 방지
        log_agent_step("InvestmentInfoCollector", "Loop limit reached -> end", {"phase": collected.get("phase")})
        return {"collected": collected, "messages": [AIMessage(content="END")]}

    # 현재 사용자 질문(마지막 HumanMessage)
    user_query = _get_user_query(messages)
    # 회사 정보(없으면 아직 resolve_ticker 전)
    company = collected.get("company")

    # ---------------------------------------------------------
    # (1) 회사 식별 단계: company가 없으면 resolve_ticker부터
    # - 사용자가 "삼전" 같은 별칭을 입력해도 회사/코드/ corp_code를 얻어오는 단계
    # ---------------------------------------------------------
    if not company:
        log_agent_step("InvestmentInfoCollector", "Plan: resolve_ticker", {})
        msg = AIMessage(
            content="Resolving company ticker...",
            tool_calls=[_tool_call("resolve_ticker", {"user_input": user_query})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (2) 뉴스 검색 단계: news_raw가 비어있으면 search_news 호출
    # - 회사명 + 사용자 질문을 합쳐서 검색 질의를 만들고,
    #   뉴스 검색 API(or 크롤러)로 관련 기사 목록을 가져온다.
    # ---------------------------------------------------------
    if collected.get("news_raw") is None:
        q = company.get("company_name") or ""
        # 사용자 질문을 섞되 너무 길면 회사명 중심으로 동작하게끔 구성
        query = f"{q} {user_query}".strip() if q else user_query
        log_agent_step("InvestmentInfoCollector", "Plan: search_news", {"query": query})
        msg = AIMessage(
            content="Searching news...",
            tool_calls=[_tool_call("search_news", {"query": query})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (3) URL 추출 단계: urls가 아직 없으면 extract_urls_from_search_result
    # - search_news 결과(raw dict)에서 실제 기사 링크만 뽑아서 urls 리스트로 만든다.
    # ---------------------------------------------------------
    if collected.get("urls") is None:
        log_agent_step("InvestmentInfoCollector", "Plan: extract_urls_from_search_result", {})
        msg = AIMessage(
            content="Extracting URLs...",
            tool_calls=[_tool_call("extract_urls_from_search_result", {"result": collected.get("news_raw")})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (4) 기사 본문 fetch 단계: urls 중 1~2개만 본문을 가져온다
    # - 너무 많은 기사 fetch는 비용/시간 증가 → 여기서는 최대 2개만 수집
    # - fetch_article_index로 다음에 가져올 url을 가리킨다.
    # ---------------------------------------------------------
    urls: List[str] = collected.get("urls") or []
    idx = int(collected.get("fetch_article_index") or 0)
    articles: List[Dict[str, Any]] = collected.get("articles") or []

    if len(articles) < 2 and idx < len(urls):
        url = urls[idx]
        log_agent_step("InvestmentInfoCollector", "Plan: fetch_article_from_url", {"url": url, "idx": idx})
        msg = AIMessage(
            content="Fetching article...",
            tool_calls=[_tool_call("fetch_article_from_url", {"url": url})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (5) 재무정보 단계(조건부):
    # - 사용자의 질문이 재무/실적 관련일 때만 1회 호출
    # - financials가 None일 때만 실행해서 중복 호출 방지
    # ---------------------------------------------------------
    if _wants_financials(user_query) and collected.get("financials") is None:
        corp_code = company.get("corp_code")
        bsns_year = _default_bsns_year()
        log_agent_step("InvestmentInfoCollector", "Plan: get_financial_statement", {"corp_code": corp_code, "bsns_year": bsns_year})
        msg = AIMessage(
            content="Fetching financial statement...",
            tool_calls=[_tool_call("get_financial_statement", {"corp_code": corp_code, "bsns_year": bsns_year, "report_type": "FY"})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (6) KB 저장 단계:
    # - 앞에서 뉴스 snippet, 기사 본문, 재무 요약 등을 kb_save_queue에 쌓아둠
    # - 큐가 비어있지 않으면 add_many_to_invest_kb로 "배치 저장" 1번 수행
    # ---------------------------------------------------------
    if collected.get("kb_save_queue"):
        queue = collected["kb_save_queue"]
        contents = [q["content"] for q in queue]
        metadatas = [q["metadata"] for q in queue]
        log_agent_step("InvestmentInfoCollector", "Plan: add_many_to_invest_kb", {"count": len(contents)})
        msg = AIMessage(
            content="Saving collected documents to KB...",
            tool_calls=[_tool_call("add_many_to_invest_kb", {"contents": contents, "metadatas": metadatas})],
        )
        return {"collected": collected, "messages": [msg]}

    # ---------------------------------------------------------
    # (7) 종료:
    # - 위에서 더 할 일이 없으면 END로 마무리
    # ---------------------------------------------------------
    log_agent_step("InvestmentInfoCollector", "Plan: end", {"phase": collected.get("phase")})
    return {"collected": collected, "messages": [AIMessage(content="END")]}


# =========================================================
# 2) accumulate 노드: Tool 실행 결과를 state.collected에 "누적"한다
# ---------------------------------------------------------
# ToolNode가 tool을 실행하면 ToolMessage가 messages에 추가된다.
# accumulate()는 방금 들어온 ToolMessage를 보고
# - 어떤 tool 결과인지(tool_name)
# - 성공/실패인지(status)
# 를 판단해서 collected를 업데이트한다.
#
# 또한 "KB에 저장할 텍스트"를 kb_save_queue에 쌓아두는 역할도 한다.
# (즉, tool 실행의 'side effect 정리/저장' 단계)
# =========================================================
def accumulate(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    # ToolNode 직후가 아니라면 아무것도 하지 않음
    if not messages or not isinstance(messages[-1], ToolMessage):
        return {"collected": collected}

    tm: ToolMessage = messages[-1]
    tool_name = getattr(tm, "name", None)
    content = tm.content

    log_agent_step("InvestmentInfoCollector", "Accumulate tool result", {"tool": tool_name})

    # ---------------------------------------------------------
    # (A) resolve_ticker 결과 처리:
    # - 성공이면 company 정보를 collected["company"]에 저장
    # - 실패면 errors에 기록하고 phase를 failed로
    # ---------------------------------------------------------
    if tool_name == "resolve_ticker" and isinstance(content, dict):
        if content.get("status") == "success":
            collected["company"] = {
                "company_name": content.get("company_name"),
                "stock_code": content.get("stock_code"),
                "corp_code": content.get("corp_code"),
            }
            collected["phase"] = "resolved"
        else:
            collected["phase"] = "failed"
            collected["errors"].append({"tool": "resolve_ticker", "content": content})

    # ---------------------------------------------------------
    # (B) search_news 결과 처리:
    # - 원본 dict는 news_raw에 저장
    # - 성공이면 items를 news에 저장 + phase 갱신
    # - 그리고 각 뉴스 item을 KB에 저장할 "snippet 문서"로 만들어 큐에 넣는다
    # ---------------------------------------------------------
    elif tool_name == "search_news" and isinstance(content, dict):
        collected["news_raw"] = content
        if content.get("status") == "success":
            items = content.get("items", [])
            collected["news"] = items
            collected["phase"] = "news_fetched"

            # 뉴스 snippet도 저장 큐에 넣기 (나중에 add_many_to_invest_kb에서 일괄 저장)
            company = collected.get("company") or {}
            for it in items:
                save_text = (
                    "[NEWS]\n"
                    f"Title: {it.get('title')}\n"
                    f"PublishedAt: {it.get('published_at')}\n"
                    f"URL: {it.get('url')}\n"
                    f"Summary: {it.get('summary')}\n"
                )
                collected["kb_save_queue"].append({
                    "content": save_text,
                    "metadata": {
                        "type": "news_snippet",
                        "url": it.get("url"),
                        "id": it.get("id"),
                        "published_at": it.get("published_at"),
                        "company_name": company.get("company_name"),
                        "stock_code": company.get("stock_code"),
                        "corp_code": company.get("corp_code"),
                        "source": it.get("source"),
                    }
                })
        else:
            collected["news"] = []
            collected["phase"] = "news_not_found"
            collected["errors"].append({"tool": "search_news", "content": content})

    # ---------------------------------------------------------
    # (C) extract_urls_from_search_result 결과 처리:
    # - content가 list면 urls로 저장
    # - 아니면 빈 리스트로 처리(방어)
    # ---------------------------------------------------------
    elif tool_name == "extract_urls_from_search_result":
        if isinstance(content, list):
            collected["urls"] = content
        else:
            collected["urls"] = []
        collected["phase"] = "urls_extracted"

    # ---------------------------------------------------------
    # (D) fetch_article_from_url 결과 처리:
    # - 다음 url로 넘어가도록 fetch_article_index는 무조건 +1
    # - 성공이면 articles에 본문 저장 + KB 저장용 문서를 큐에 넣음
    # - 실패면 article_errors에 쌓아둠
    # ---------------------------------------------------------
    elif tool_name == "fetch_article_from_url" and isinstance(content, dict):
        collected["fetch_article_index"] = int(collected.get("fetch_article_index", 0)) + 1

        if content.get("status") == "success":
            collected.setdefault("articles", []).append(content)
            collected["phase"] = "article_fetched"

            company = collected.get("company") or {}
            body = content.get("body") or ""
            save_text = (
                "[ARTICLE]\n"
                f"Title: {content.get('title')}\n"
                f"PublishedAt: {content.get('published_at')}\n"
                f"URL: {content.get('url')}\n"
                f"Publisher: {content.get('publisher')}\n\n"
                f"{body}"
            )
            collected["kb_save_queue"].append({
                "content": save_text,
                "metadata": {
                    "type": "news_article",
                    "url": content.get("url"),
                    "published_at": content.get("published_at"),
                    "company_name": company.get("company_name"),
                    "stock_code": company.get("stock_code"),
                    "corp_code": company.get("corp_code"),
                    "publisher": content.get("publisher"),
                }
            })
        else:
            collected.setdefault("article_errors", []).append(content)
            collected["phase"] = "article_fetch_error"

    # ---------------------------------------------------------
    # (E) get_financial_statement 결과 처리:
    # - financials에 저장 + phase 갱신
    # - 성공이면 핵심 계정(key_accounts)을 텍스트로 만들어 KB 큐에 추가
    # ---------------------------------------------------------
    elif tool_name == "get_financial_statement" and isinstance(content, dict):
        collected["financials"] = content
        collected["phase"] = "financials_done"

        if content.get("status") == "success":
            company = collected.get("company") or {}
            ka = content.get("key_accounts") or {}
            save_text = (
                "[FINANCIALS]\n"
                f"CorpCode: {content.get('corp_code')}\n"
                f"Year: {content.get('bsns_year')} Report: {content.get('report_type')}\n"
                f"KeyAccounts: {ka}"
            )
            collected["kb_save_queue"].append({
                "content": save_text,
                "metadata": {
                    "type": "financials",
                    "corp_code": company.get("corp_code"),
                    "company_name": company.get("company_name"),
                    "stock_code": company.get("stock_code"),
                    "bsns_year": content.get("bsns_year"),
                    "report_type": content.get("report_type"),
                }
            })
        else:
            collected["errors"].append({"tool": "get_financial_statement", "content": content})

    # ---------------------------------------------------------
    # (F) add_many_to_invest_kb 결과 처리:
    # - 저장 결과를 kb_saved에 기록
    # - 큐는 비워서(중복 저장 방지) 다음 루프에서 종료로 갈 수 있게 함
    # ---------------------------------------------------------
    elif tool_name == "add_many_to_invest_kb" and isinstance(content, dict):
        collected.setdefault("kb_saved", []).append(content)
        collected["kb_save_queue"] = []
        collected["phase"] = "kb_saved"

    # ---------------------------------------------------------
    # (G) 그 외 예상 못한 tool 결과는 errors로 기록
    # ---------------------------------------------------------
    else:
        collected["errors"].append({"tool": tool_name, "content": content})

    return {"collected": collected}


# =========================================================
# 3) 라우팅 함수: planner 결과에 tool_calls가 있으면 tools로, 아니면 종료
# ---------------------------------------------------------
# plan_next_action이 반환한 마지막 메시지가
# - AIMessage + tool_calls 있음 → ToolNode(tools)로 이동
# - 그 외(END 메시지 등) → 그래프 종료
# =========================================================
def route_after_plan(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"


# =========================================================
# 4) 그래프 구성: plan → tools → accumulate → plan ... 반복
# ---------------------------------------------------------
# 여기서는 LangGraph StateGraph를 이용해 노드/엣지를 연결한다.
#
# 노드:
# - plan_next_action: 다음 tool 결정
# - tools: 실제 tool 실행(ToolNode)
# - accumulate: tool 결과를 collected에 반영
#
# 엣지:
# - plan_next_action -> (조건) tools 또는 END
# - tools -> accumulate
# - accumulate -> plan_next_action (다음 루프)
# =========================================================

# ToolNode에서 실행 가능한 tool 리스트
info_collect_tools = [
    resolve_ticker,
    search_news,
    extract_urls_from_search_result,
    fetch_article_from_url,
    get_financial_statement,
    add_many_to_invest_kb,
]

workflow = StateGraph(InfoCollectorAgentState)

workflow.add_node("plan_next_action", plan_next_action)
workflow.add_node("tools", ToolNode(info_collect_tools))
workflow.add_node("accumulate", accumulate)

# 시작 노드는 planner
workflow.set_entry_point("plan_next_action")

# planner 결과에 따라 다음 노드를 조건 분기
workflow.add_conditional_edges(
    "plan_next_action",
    route_after_plan,
    {
        "tools": "tools",  # tool_calls 있으면 실행하러 감
        "end": END,        # 없으면 종료
    },
)

# tool 실행 후 결과 누적, 누적 후 다시 planner로
workflow.add_edge("tools", "accumulate")
workflow.add_edge("accumulate", "plan_next_action")

# 컴파일된 그래프 객체(외부에서 import 해서 사용)
info_collect_graph = workflow.compile()
