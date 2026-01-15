# app/agents/subgraphs/info_collector.py

from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import json
import ast

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.logger import logger
from app.agents.state import InfoCollectorAgentState
from app.agents.tools import (
    get_portfolio_stocks,
    resolve_ticker,
    search_news,
    extract_urls_from_search_result,
    fetch_article_from_url,
    get_financial_statement,
    add_many_to_invest_kb,
    analyze_invest_query,
)
from app.core.logger import log_agent_step
from app.core.db import engine


# ✅ [신규] 현재 날짜 기준으로 가장 최신 보고서(연도, 타입)를 계산하는 함수
def _get_latest_report_params() -> Dict[str, Any]:
    now = datetime.now()
    year = now.year
    month = now.month
    day = now.day

    # DART 제출 기한을 보수적으로 적용하여 타겟 설정
    if month < 4:
        # 1월~3월: 작년 사업보고서(FY)도 아직 안 나옴 -> 작년 3분기(Q3)가 최신
        return {"bsns_year": year - 1, "report_type": "Q3"}

    elif month == 4 or (month == 5 and day <= 15):
        # 4월 ~ 5월 15일: 작년 사업보고서(FY) 확정됨
        return {"bsns_year": year - 1, "report_type": "FY"}

    elif month < 8 or (month == 8 and day <= 14):
        # 5월 16일 ~ 8월 14일: 올해 1분기 보고서(Q1) 확정됨
        return {"bsns_year": year, "report_type": "Q1"}

    elif month < 11 or (month == 11 and day <= 14):
        # 8월 15일 ~ 11월 14일: 올해 반기 보고서(H1) 확정됨
        return {"bsns_year": year, "report_type": "H1"}

    else:
        # 11월 15일 ~ 12월: 올해 3분기 보고서(Q3) 확정됨
        return {"bsns_year": year, "report_type": "Q3"}


def _tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
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


def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """ChromaDB는 None 값을 허용하지 않으므로 필터링"""
    cleaned = {k: v for k, v in metadata.items() if v is not None}
    if len(cleaned) != len(metadata):
        logger.info(f"Filtered metadata: {set(metadata.keys()) - set(cleaned.keys())} had None values")
    return cleaned


# -------------------------
# 1) Planner    analyze_invest_query,
# -------------------------
def plan_next_action(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    # 초기화
    collected.setdefault("phase", "start")
    collected.setdefault("fetch_article_index", 0)
    collected.setdefault("kb_save_queue", [])
    collected.setdefault("kb_saved", [])
    collected.setdefault("news", None)
    collected.setdefault("news_raw", None)
    collected.setdefault("urls", None)
    collected.setdefault("articles", [])
    collected.setdefault("financials", None)
    collected.setdefault("errors", [])
    collected.setdefault("loop_count", 0)

    # 포트폴리오용 상태 추가
    collected.setdefault("portfolio_mode", False)
    collected.setdefault("portfolio_loaded", False)
    collected.setdefault("portfolio_holdings", [])
    collected.setdefault("portfolio_index", 0)
    collected.setdefault("portfolio_results", [])

    collected["loop_count"] += 1
    if collected["loop_count"] > 50:
        log_agent_step("InvestmentInfoCollector", "Loop limit reached -> end", {"phase": collected.get("phase")})
        return {"collected": collected, "messages": [AIMessage(content="END")]}

    user_query = _get_user_query(messages)

    # ✅ 0) 아직 질의 분석이 안 되어 있으면 LLM 분석 툴 호출
    if not collected.get("query_analysis_done"):
        log_agent_step("InvestmentInfoCollector", "Plan: analyze_invest_query", {"user_query": user_query})
        msg = AIMessage(
            content="Analyzing user query...",
            tool_calls=[_tool_call("analyze_invest_query", {"user_query": user_query})],
        )
        return {"collected": collected, "messages": [msg]}

    # ✅ 1) 분석 결과 기반 분기
    query_type = collected.get("query_type")

    if query_type == "PORTFOLIO":
        collected["portfolio_mode"] = True

    # (B) 포트폴리오 로직
    if collected["portfolio_mode"]:
        user_id = state.get("user_id") or (state.get("user") or {}).get("user_id")
        if not user_id:
            collected["errors"].append({"tool": "get_portfolio_stocks", "content": "user_id missing in state"})
            return {"collected": collected, "messages": [AIMessage(content="END")]}

        if not collected["portfolio_loaded"]:
            log_agent_step("InvestmentInfoCollector", "Plan: get_portfolio_stocks", {"user_id": user_id})
            msg = AIMessage(
                content="Loading portfolio stocks...",
                tool_calls=[_tool_call("get_portfolio_stocks", {"user_id": user_id})],
            )
            return {"collected": collected, "messages": [msg]}

        idx = int(collected.get("portfolio_index") or 0)
        holdings = collected.get("portfolio_holdings") or []

        if idx >= len(holdings):
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

        if not collected.get("company"):
            h = holdings[idx]
            user_input = h.get("ticker") or h.get("name") or h.get("stock_id")
            log_agent_step("InvestmentInfoCollector", "Plan: resolve_ticker (portfolio item)",
                           {"idx": idx, "user_input": user_input})
            msg = AIMessage(
                content="Resolving portfolio company...",
                tool_calls=[_tool_call("resolve_ticker", {"user_input": user_input})],
            )
            return {"collected": collected, "messages": [msg]}

    # --- 단일 기업/포트폴리오 공통 플로우 ---
    company = collected.get("company")

    # 1) 회사 식별
    if not company and not collected.get("portfolio_mode"):
        # COMPANY / OTHER 타입일 때만 시도 (PORTFOLIO는 포트폴리오 로직에서 처리)
        candidates = collected.get("company_candidates") or []

        if candidates:
            # 일단 첫 번째 후보를 사용 (나중에 멀티기업 확장 가능)
            first = candidates[0]
            user_input_for_resolve = first.get("ticker_hint") or first.get("name") or first.get("raw_span")
        else:
            # 후보가 없으면 fallback: 전체 user_query
            user_input_for_resolve = user_query

        log_agent_step(
            "InvestmentInfoCollector",
            "Plan: resolve_ticker (from analysis)",
            {"user_input": user_input_for_resolve},
        )
        msg = AIMessage(
            content="Resolving company ticker...",
            tool_calls=[_tool_call("resolve_ticker", {"user_input": user_input_for_resolve})],
        )
        return {"collected": collected, "messages": [msg]}

    # 2) 뉴스 검색
    if collected.get("news_raw") is None:
        company_name = company.get("company_name") or ""
        # ✅ [수정] 검색어 단순화: 사용자 쿼리 전체를 넣으면 검색 결과가 안 나옴. 회사명만 사용.
        query = company_name.strip()
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

    # 4) 기사 본문 fetch
    urls: List[str] = collected.get("urls") or []
    idx = int(collected.get("fetch_article_index") or 0)
    articles: List[Dict[str, Any]] = collected.get("articles") or []

    # 기사 2개까지만 수집 (테스트용)
    if len(articles) < 20 and idx < len(urls):
        url = urls[idx]
        log_agent_step("InvestmentInfoCollector", "Plan: fetch_article_from_url", {"url": url, "idx": idx})
        msg = AIMessage(
            content="Fetching article...",
            tool_calls=[_tool_call("fetch_article_from_url", {"url": url})],
        )
        return {"collected": collected, "messages": [msg]}

    # 5) 재무정보
    # corp_code 없는 경우에는 재무제표 수집을 시도하지 않고, 한 번만 스킵 표시 후 넘어간다.
    if collected.get("financials") is None:
        corp_code = (company or {}).get("corp_code")

        if not corp_code:
            # ✅ 재무제표 스킵 처리 (무한 루프 방지용)
            log_agent_step(
                "InvestmentInfoCollector",
                "Skip get_financial_statement: corp_code missing",
                {"company": company},
            )
            collected["financials"] = {
                "status": "skipped",
                "reason": "corp_code_missing",
            }
        else:
            # ✅ corp_code 가 있는 경우에만 DART 호출
            target_params = _get_latest_report_params()
            bsns_year = target_params["bsns_year"]
            report_type = target_params["report_type"]

            log_agent_step(
                "InvestmentInfoCollector",
                "Plan: get_financial_statement",
                {"corp_code": corp_code, "target": target_params},
            )

            msg = AIMessage(
                content=f"Fetching financial statement ({bsns_year} {report_type})...",
                tool_calls=[_tool_call("get_financial_statement", {
                    "corp_code": corp_code,
                    "bsns_year": bsns_year,
                    "report_type": report_type
                })],
            )
            return {"collected": collected, "messages": [msg]}

    # 6) KB 저장 큐 처리
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
# 2) Tool 결과 누적 (Accumulate)
# -------------------------
def accumulate(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    collected: Dict[str, Any] = state.get("collected") or {}

    if not messages or not isinstance(messages[-1], ToolMessage):
        return {"collected": collected}

    tm: ToolMessage = messages[-1]
    tool_name = getattr(tm, "name", None)
    content = tm.content

    # 파싱 로직 강화
    if isinstance(content, str):
        content = content.strip()
        parsed = False
        try:
            content = json.loads(content)
            parsed = True
        except Exception:
            pass

        if not parsed:
            try:
                content = ast.literal_eval(content)
            except Exception:
                pass

    log_agent_step("InvestmentInfoCollector", "Accumulate tool result", {"tool": tool_name})

    # ✅ 새로 추가: analyze_invest_query 결과 처리
    if tool_name == "analyze_invest_query" and isinstance(content, dict):
        if content.get("status") == "success":
            collected["query_analysis_done"] = True
            qtype = (content.get("query_type") or "").upper()
            if qtype not in ["TERM", "PORTFOLIO", "COMPANY", "OTHER"]:
                qtype = "OTHER"
            collected["query_type"] = qtype

            # COMPANY 쿼리라면 LLM이 뽑은 기업 목록 저장
            companies = content.get("companies") or []
            collected["company_candidates"] = companies
            collected["phase"] = "query_analyzed"
        else:
            # 분석 실패하면 그냥 OTHER로 두고, 이후 로직에서 user_query 그대로 사용
            collected["query_analysis_done"] = True
            collected["query_type"] = "OTHER"
            collected["company_candidates"] = []
            collected["errors"].append({"tool": "analyze_invest_query", "content": content})
            collected["phase"] = "query_analysis_failed"

    elif tool_name == "get_portfolio_stocks" and isinstance(content, dict):
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

    elif tool_name == "search_news" and isinstance(content, dict):
        collected["news_raw"] = content
        if content.get("status") == "success":
            items = content.get("items", [])
            collected["news"] = items
            collected["phase"] = "news_fetched"

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
                    "metadata": _clean_metadata({
                        "type": "news_snippet",
                        "url": it.get("url"),
                        "id": it.get("id"),
                        "published_at": it.get("published_at"),
                        "company_name": company.get("company_name"),
                        "stock_code": company.get("stock_code"),
                        "corp_code": company.get("corp_code"),
                        "source": it.get("source"),
                    })
                })
        else:
            collected["news"] = []
            collected["phase"] = "news_not_found"
            collected["errors"].append({"tool": "search_news", "content": content})

    elif tool_name == "extract_urls_from_search_result":
        if isinstance(content, list):
            collected["urls"] = content
        elif isinstance(content, str) and content.strip().startswith("["):
            try:
                collected["urls"] = json.loads(content)
            except:
                try:
                    collected["urls"] = ast.literal_eval(content)
                except:
                    collected["urls"] = []
        else:
            collected["urls"] = []
        collected["phase"] = "urls_extracted"

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
                "metadata": _clean_metadata({
                    "type": "news_article",
                    "url": content.get("url"),
                    "published_at": content.get("published_at"),
                    "company_name": company.get("company_name"),
                    "stock_code": company.get("stock_code"),
                    "corp_code": company.get("corp_code"),
                    "publisher": content.get("publisher"),
                })
            })
        else:
            collected.setdefault("article_errors", []).append(content)
            collected["phase"] = "article_fetch_error"

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
                "metadata": _clean_metadata({
                    "type": "financials",
                    "corp_code": company.get("corp_code"),
                    "company_name": company.get("company_name"),
                    "stock_code": company.get("stock_code"),
                    "bsns_year": content.get("bsns_year"),
                    "report_type": content.get("report_type"),
                })
            })
        else:
            collected["errors"].append({"tool": "get_financial_statement", "content": content})

    elif tool_name == "add_many_to_invest_kb" and isinstance(content, dict):
        collected.setdefault("kb_saved", []).append(content)
        collected["kb_save_queue"] = []
        collected["phase"] = "kb_saved"

    else:
        collected["errors"].append({"tool": tool_name, "content": content})

    # 루프 제어
    user_query = _get_user_query(messages)
    if collected.get("portfolio_mode") and collected.get("portfolio_loaded"):
        idx = int(collected.get("portfolio_index") or 0)
        holdings = collected.get("portfolio_holdings") or []

        # ✅ 항상 뉴스 + 재무제표를 둘 다 가져오는 기준으로 done 정의
        urls = collected.get("urls") or []
        fetch_idx = int(collected.get("fetch_article_index") or 0)
        articles = collected.get("articles") or []

        news_done = (len(articles) >= 10) or (fetch_idx >= len(urls) and collected.get("urls") is not None)
        fin_done = collected.get("financials") is not None

        done = news_done and fin_done

        if done and idx < len(holdings):
            company = collected.get("company") or {}
            collected["portfolio_results"].append({
                "company": company,
                "news": collected.get("news") or [],
                "articles": collected.get("articles") or [],
                "financials": collected.get("financials"),
            })
            collected["portfolio_index"] = idx + 1
            _reset_company_scope(collected)
            collected["phase"] = "portfolio_next"

    return {"collected": collected}


# -------------------------
# 3) Routing & Graph
# -------------------------
def route_after_plan(state: InfoCollectorAgentState):
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"


info_collect_tools = [
    get_portfolio_stocks,
    resolve_ticker,
    search_news,
    extract_urls_from_search_result,
    fetch_article_from_url,
    get_financial_statement,
    add_many_to_invest_kb,
    analyze_invest_query,
]

workflow = StateGraph(InfoCollectorAgentState)
workflow.add_node("plan_next_action", plan_next_action)
workflow.add_node("tools", ToolNode(info_collect_tools))
workflow.add_node("accumulate", accumulate)

workflow.set_entry_point("plan_next_action")
workflow.add_conditional_edges("plan_next_action", route_after_plan, {"tools": "tools", "end": END})
workflow.add_edge("tools", "accumulate")
workflow.add_edge("accumulate", "plan_next_action")

info_collect_graph = workflow.compile()

