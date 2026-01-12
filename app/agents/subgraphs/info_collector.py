# app/agents/subgraphs/info_collector.py

from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.state import InfoCollectorAgentState
from app.agents.tools import (
    get_portfolio_stocks,
    resolve_ticker,
    search_news,
    extract_urls_from_search_result,
    fetch_article_from_url,
    get_financial_statement,
    add_many_to_invest_kb,
)
from app.core.logger import log_agent_step

from app.core.db import engine


# -------------------------
# 0) 간단 휴리스틱
# -------------------------
FIN_KEYWORDS = ["실적", "매출", "영업이익", "순이익", "재무", "재무제표", "손익", "자산", "부채", "자본", "ROE", "PER", "PBR"]

PF_KEYWORDS = ["포트폴리오", "보유", "내 종목", "내 주식", "내가 가진", "내가 보유한"]

def _wants_portfolio(user_query: str) -> bool:
    q = (user_query or "").lower()
    return any(k.lower() in q for k in PF_KEYWORDS)


def _wants_financials(user_query: str) -> bool:
    q = (user_query or "").lower()
    return any(k.lower() in q for k in FIN_KEYWORDS)

def _default_bsns_year() -> int:
    # 1월 초면 전년도 기준으로 먼저 시도
    return datetime.now().year - 1

def _tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    # ToolNode가 인식하는 tool_call 포맷
    return {"name": name, "args": args, "id": str(uuid.uuid4())}


def _get_user_query(messages: List[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return ""

def _reset_company_scope(collected: Dict[str, Any]):
    collected["company"] = None
    collected["news"] = None
    collected["news_raw"] = None
    collected["urls"] = None
    collected["articles"] = []
    collected["financials"] = None
    collected["fetch_article_index"] = 0


# -------------------------
# 1) Planner: 다음 1개 tool_call을 "코드로" 결정해서 AIMessage로 반환
# -------------------------
def plan_next_action(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    # 초기화
    collected.setdefault("phase", "start")
    collected.setdefault("fetch_article_index", 0)
    collected.setdefault("kb_save_queue", [])
    collected.setdefault("kb_saved", [])
    collected.setdefault("news", None)         # search_news 결과 items 저장용
    collected.setdefault("news_raw", None)     # search_news 결과 dict 원본 저장용
    collected.setdefault("urls", None)
    collected.setdefault("articles", [])
    collected.setdefault("financials", None)
    collected.setdefault("errors", [])
    collected.setdefault("loop_count", 0)

    # ✅ 포트폴리오용 상태 추가
    collected.setdefault("portfolio_mode", False)
    collected.setdefault("portfolio_loaded", False)
    collected.setdefault("portfolio_holdings", [])
    collected.setdefault("portfolio_index", 0)
    collected.setdefault("portfolio_results", [])

    collected["loop_count"] += 1
    if collected["loop_count"] > 50:
        # 안전장치: 무한루프 방지
        log_agent_step("InvestmentInfoCollector", "Loop limit reached -> end", {"phase": collected.get("phase")})
        return {"collected": collected, "messages": [AIMessage(content="END")]}

    user_query = _get_user_query(messages)

    # ✅ (A) 포트폴리오 요청이면 모드 ON
    if _wants_portfolio(user_query):
        collected["portfolio_mode"] = True

    # ✅ (B) 포트폴리오 모드면: 1) 종목 로드부터
    if collected["portfolio_mode"]:
        # user_id는 state에 있다고 가정 (없으면 state 구조에 추가 필요)
        user_id = state.get("user_id") or (state.get("user") or {}).get("user_id")
        if not user_id:
            # user_id가 없으면 여기서 종료(또는 errors에 기록)
            collected["errors"].append({"tool": "get_portfolio_stocks", "content": "user_id missing in state"})
            return {"collected": collected, "messages": [AIMessage(content="END")]}

        if not collected["portfolio_loaded"]:
            log_agent_step("InvestmentInfoCollector", "Plan: get_portfolio_stocks", {"user_id": user_id})
            msg = AIMessage(
                content="Loading portfolio stocks...",
                tool_calls=[_tool_call("get_portfolio_stocks", {"user_id": user_id})],
            )
            return {"collected": collected, "messages": [msg]}

        # ✅ (C) 종목을 하나씩 꺼내서 기존 단일 기업 플로우 재사용
        idx = int(collected.get("portfolio_index") or 0)
        holdings = collected.get("portfolio_holdings") or []

        # 모든 종목 처리 끝
        if idx >= len(holdings):
            # 저장 큐 남아있으면 저장 후 END 하게 놔둠(기존 로직이 처리)
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

            return {"collected": collected, "messages": [AIMessage(content="END")]}

        # 아직 처리 중인 종목이 있는데 company가 비어있으면 → resolve_ticker 호출
        if not collected.get("company"):
            h = holdings[idx]
            # ticker 우선, 없으면 name
            user_input = h.get("ticker") or h.get("name") or h.get("stock_id")
            log_agent_step("InvestmentInfoCollector", "Plan: resolve_ticker (portfolio item)",
                           {"idx": idx, "user_input": user_input})
            msg = AIMessage(
                content="Resolving portfolio company...",
                tool_calls=[_tool_call("resolve_ticker", {"user_input": user_input})],
            )
            return {"collected": collected, "messages": [msg]}

        # 여기서부터는 기존 “단일 기업 플로우”가 계속 진행되도록 아래 기존 코드로 자연스럽게 떨어짐

    # --- 이하 기존 로직 그대로: company resolve → search_news → extract_urls → fetch_article ... ---
    company = collected.get("company")

    # 1) 회사 식별
    if not company:
        log_agent_step("InvestmentInfoCollector", "Plan: resolve_ticker", {})
        msg = AIMessage(
            content="Resolving company ticker...",
            tool_calls=[_tool_call("resolve_ticker", {"user_input": user_query})],
        )
        return {"collected": collected, "messages": [msg]}

    # 2) 뉴스 검색
    if collected.get("news_raw") is None:
        q = company.get("company_name") or ""
        # 사용자 질문 의도를 조금 섞되, 너무 길면 회사명 중심
        query = f"{q} {user_query}".strip() if q else user_query
        log_agent_step("InvestmentInfoCollector", "Plan: search_news", {"query": query})
        msg = AIMessage(
            content="Searching news...",
            tool_calls=[_tool_call("search_news", {"query": query})],
        )
        return {"collected": collected, "messages": [msg]}

    # 3) URL 추출
    if collected.get("urls") is None:
        log_agent_step("InvestmentInfoCollector", "Plan: extract_urls_from_search_result", {})
        msg = AIMessage(
            content="Extracting URLs...",
            tool_calls=[_tool_call("extract_urls_from_search_result", {"result": collected.get("news_raw")})],
        )
        return {"collected": collected, "messages": [msg]}

    # 4) 기사 본문 1~2개 fetch
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

    # 5) 재무정보(질문이 재무성일 때만 1회)
    if _wants_financials(user_query) and collected.get("financials") is None:
        corp_code = company.get("corp_code")
        bsns_year = _default_bsns_year()
        log_agent_step("InvestmentInfoCollector", "Plan: get_financial_statement", {"corp_code": corp_code, "bsns_year": bsns_year})
        msg = AIMessage(
            content="Fetching financial statement...",
            tool_calls=[_tool_call("get_financial_statement", {"corp_code": corp_code, "bsns_year": bsns_year, "report_type": "FY"})],
        )
        return {"collected": collected, "messages": [msg]}

    # 6) KB 저장 큐 있으면 배치 저장(강제)
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

    # 7) 끝
    log_agent_step("InvestmentInfoCollector", "Plan: end", {"phase": collected.get("phase")})
    return {"collected": collected, "messages": [AIMessage(content="END")]}


# -------------------------
# 2) Tool 결과 누적(accumulate)
# -------------------------
def accumulate(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    if not messages or not isinstance(messages[-1], ToolMessage):
        return {"collected": collected}

    tm: ToolMessage = messages[-1]
    tool_name = getattr(tm, "name", None)
    content = tm.content

    log_agent_step("InvestmentInfoCollector", "Accumulate tool result", {"tool": tool_name})

    # get_portfolio_stocks
    if tool_name == "get_portfolio_stocks" and isinstance(content, dict):
        if content.get("status") == "success":
            collected["portfolio_holdings"] = content.get("holdings", [])
            collected["portfolio_loaded"] = True
            collected["portfolio_index"] = 0
            collected["portfolio_results"] = []
            collected["phase"] = "portfolio_loaded"
        else:
            collected["portfolio_loaded"] = True
            collected["portfolio_holdings"] = []
            collected["errors"].append({"tool": "get_portfolio_stocks", "content": content})
            collected["phase"] = "portfolio_load_failed"

    # resolve_ticker
    elif tool_name == "resolve_ticker" and isinstance(content, dict):
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

    # search_news
    elif tool_name == "search_news" and isinstance(content, dict):
        collected["news_raw"] = content
        if content.get("status") == "success":
            items = content.get("items", [])
            collected["news"] = items
            collected["phase"] = "news_fetched"

            # 뉴스 snippet도 저장 큐에 넣기
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

    # extract_urls_from_search_result
    elif tool_name == "extract_urls_from_search_result":
        if isinstance(content, list):
            collected["urls"] = content
        else:
            collected["urls"] = []
        collected["phase"] = "urls_extracted"

    # fetch_article_from_url
    elif tool_name == "fetch_article_from_url" and isinstance(content, dict):
        # 다음 index로 이동(성공/실패 무관)
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

    # get_financial_statement
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

    # add_many_to_invest_kb
    elif tool_name == "add_many_to_invest_kb" and isinstance(content, dict):
        collected.setdefault("kb_saved", []).append(content)
        collected["kb_save_queue"] = []
        collected["phase"] = "kb_saved"

    else:
        collected["errors"].append({"tool": tool_name, "content": content})

    # accumulate 맨 마지막 return 직전에 추가
    user_query = _get_user_query(messages)
    if collected.get("portfolio_mode") and collected.get("portfolio_loaded"):
        idx = int(collected.get("portfolio_index") or 0)
        holdings = collected.get("portfolio_holdings") or []

        # 현재 회사 처리 완료 조건(간단)
        wants_fin = _wants_financials(user_query)
        done = False
        if wants_fin:
            done = collected.get("financials") is not None
        else:
            # 기사 2개까지 시도했고 URLs를 다 훑었거나, articles가 2개 채워졌으면 완료
            urls = collected.get("urls") or []
            fetch_idx = int(collected.get("fetch_article_index") or 0)
            articles = collected.get("articles") or []
            done = (len(articles) >= 2) or (fetch_idx >= len(urls) and collected.get("urls") is not None)

        if done and idx < len(holdings):
            # 결과 스냅샷 저장
            company = collected.get("company") or {}
            collected["portfolio_results"].append({
                "company": company,
                "news": collected.get("news") or [],
                "articles": collected.get("articles") or [],
                "financials": collected.get("financials"),
            })

            # 다음 종목으로
            collected["portfolio_index"] = idx + 1
            _reset_company_scope(collected)
            collected["phase"] = "portfolio_next"

    return {"collected": collected}


# -------------------------
# 3) 분기: planner가 tool_calls 있으면 tools로, 없으면 end
# -------------------------
def route_after_plan(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"


# -------------------------
# 4) 그래프 구성
# -------------------------
info_collect_tools = [
    get_portfolio_stocks,
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

workflow.set_entry_point("plan_next_action")

workflow.add_conditional_edges(
    "plan_next_action",
    route_after_plan,
    {
        "tools": "tools",
        "end": END,
    },
)

workflow.add_edge("tools", "accumulate")
workflow.add_edge("accumulate", "plan_next_action")

info_collect_graph = workflow.compile()

result = info_collect_graph.invoke(
    {
        "messages": [HumanMessage(content="내 포트폴리오 기준으로 뉴스랑 재무제표 가져와줘")],
        "collected": {},
        "user_id": "u123",  # ✅ state에 user_id 넣기
    },
    config={
        "configurable": {
            "db_engine": engine,
            "join_stock_master": True,
            # vector_service, ticker_resolver 등도 필요하면 여기에 추가
        }
    }
)