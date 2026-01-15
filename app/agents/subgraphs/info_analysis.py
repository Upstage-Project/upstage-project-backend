import json
from typing import Dict, Any, List, Literal  # Literal 추가
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, ToolMessage

from app.agents.tools import (
    get_portfolio_stocks,
    resolve_ticker,
    analyze_stock_info
)
from app.core.logger import log_agent_step


# -------------------------
# State Definition
# -------------------------
class InfoAnalysisAgentState(Dict):
    messages: List[Any]
    user_id: str
    analysis_data: Dict[str, Any]
    analysis_results: List[Dict[str, Any]]
    collected: Dict[str, Any]  # info_collector에서 수집한 정보


# -------------------------
# Node 1: Plan Analysis
# -------------------------
def plan_analysis(state: InfoAnalysisAgentState):
    messages = state.get("messages", [])
    data = state.get("analysis_data") or {"targets": [], "current_idx": 0, "phase": "setup"}
    results = state.get("analysis_results") or []
    user_id = state.get("user_id")
    collected = state.get("collected", {})

    if data.get("phase") == "analyzing":
        return loop_analysis(state)

    # collected에서 포트폴리오 정보 확인
    portfolio_holdings = collected.get("portfolio_holdings", [])
    portfolio_mode = collected.get("portfolio_mode", False)

    # 포트폴리오 모드이고 holdings가 있으면 직접 사용
    if portfolio_mode and portfolio_holdings:
        targets = []
        for h in portfolio_holdings:
            targets.append({
                "name": h.get("name") or h.get("stock_id"),
                "code": h.get("ticker") or h.get("stock_id")
            })
        
        data["targets"] = targets
        data["phase"] = "analyzing"
        data["current_idx"] = 0
        
        return {"analysis_data": data}

    # 포트폴리오가 아닌 경우, 마지막 메시지에서 사용자 쿼리 추출
    user_query = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_query = msg.content
            break
        elif hasattr(msg, "content") and isinstance(msg.content, str):
            if msg.content not in ["END", "Analyzing user query...", "Loading portfolio stocks...", "Resolving company ticker...", "Saving collected documents to KB..."]:
                user_query = msg.content
                break

    if not user_query:
        user_query = messages[-1].content if messages else ""

    # ✅ END 메시지, JSON, 시스템 메시지 처리 - 분석 건너뛰기
    if not user_query or user_query in ["END", ""] or user_query.startswith("{") or user_query.startswith("["):
        data["phase"] = "analyzing"
        data["targets"] = []
        return {"analysis_data": data}

    # 단일 회사 분석
    return {
        "analysis_data": data,
        "analysis_results": results,
        "messages": [AIMessage(
            content="Resolve Ticker",
            tool_calls=[{"name": "resolve_ticker", "args": {"user_input": user_query}, "id": "resolve_call"}]
        )]
    }


# -------------------------
# Node 2: Setup Result
# -------------------------
def process_setup_result(state: InfoAnalysisAgentState):
    messages = state.get("messages")
    data = state.get("analysis_data")
    last_msg = messages[-1]

    if not isinstance(last_msg, ToolMessage):
        return {"messages": [AIMessage(content="Tool Error")]}

    try:
        content = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
    except:
        content = {}

    targets = []
    if last_msg.name == "get_portfolio_stocks" and content.get("status") == "success":
        for h in content.get("holdings", []):
            targets.append({"name": h.get("name"), "code": h.get("ticker")})
    elif last_msg.name == "resolve_ticker" and content.get("status") == "success":
        targets.append({"name": content.get("company_name"), "code": content.get("stock_code")})

    # 실패 시에도 루프 탈출을 위해 analyzing으로 강제 전환
    if not targets:
        error_json = json.dumps({"status": "error", "message": "No targets found"})
        data["phase"] = "analyzing"
        return {
            "messages": [AIMessage(content=error_json)],
            "analysis_data": data
        }

    data["targets"] = targets
    data["phase"] = "analyzing"
    data["current_idx"] = 0

    return {"analysis_data": data}


# -------------------------
# Node 3: Loop Analysis
# -------------------------
def loop_analysis(state: InfoAnalysisAgentState):
    data = state.get("analysis_data", {})
    targets = data.get("targets", [])
    idx = data.get("current_idx", 0)
    results = state.get("analysis_results") or []

    # 종료 조건
    if idx >= len(targets):
        final_json_str = json.dumps(results, ensure_ascii=False, indent=2)
        return {
            "analysis_results": results,
            "messages": [AIMessage(content=final_json_str)]
        }

    # 분석 결과 저장 로직
    last_msg = state["messages"][-1]
    if isinstance(last_msg, ToolMessage) and last_msg.name == "analyze_stock_info":
        current_target = targets[idx]
        analyzed_entry = {
            "stock_name": current_target["name"],
            "stock_code": current_target["code"],
            "analysis_report": last_msg.content
        }
        results.append(analyzed_entry)
        data["current_idx"] = idx + 1
        return {
            "analysis_data": data,
            "analysis_results": results
        }

    # 다음 분석 실행
    target = targets[idx]
    stock_name = target["name"]

    return {
        "messages": [AIMessage(
            content=f"Analyzing {stock_name}...",
            tool_calls=[{
                "name": "analyze_stock_info",
                "args": {
                    "stock_name": stock_name,
                    "context_query": f"{stock_name} 최근 주요 뉴스 실적 재무제표 이슈"
                },
                "id": f"analyze_{idx}"
            }]
        )]
    }


# -------------------------
# ✅ [NEW] Routing Logics
# -------------------------

def route_main(state: InfoAnalysisAgentState):
    """Plan 단계에서 툴 호출인지 판단"""
    messages = state.get("messages")
    last_msg = messages[-1]

    # Plan이 툴을 호출했으면 tools로
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"

    return END  # 비정상 상황


def route_after_tools(state: InfoAnalysisAgentState) -> Literal["process_setup_result", "loop_analysis"]:
    """
    🛠️ 핵심 수정: Tools 실행 후 어디로 갈지 결정하는 라우터
    """
    messages = state.get("messages")
    last_msg = messages[-1]  # ToolMessage
    tool_name = last_msg.name

    # 1. 셋업 툴(종목확인, 포트폴리오)이면 -> 결과 처리 노드로
    if tool_name in ["resolve_ticker", "get_portfolio_stocks"]:
        return "process_setup_result"

    # 2. 분석 툴이면 -> 루프 노드로 (결과 저장 및 다음 종목)
    elif tool_name == "analyze_stock_info":
        return "loop_analysis"

    return "loop_analysis"  # 기본값


def route_after_loop(state: InfoAnalysisAgentState):
    """Loop 단계에서 계속할지, 툴 호출할지, 끝낼지 결정"""
    messages = state.get("messages")
    last_msg = messages[-1]

    # 최종 결과(AIMessage + No tool call) -> 끝
    if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
        return END

    # 툴 호출(analyze_stock_info) -> Tools
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"

    # ToolMessage가 왔으면(분석완료) -> 다시 Loop로
    if isinstance(last_msg, ToolMessage):
        return "loop_analysis"

    return END


# -------------------------
# Graph Construction
# -------------------------
workflow = StateGraph(InfoAnalysisAgentState)

workflow.add_node("plan_analysis", plan_analysis)
workflow.add_node("process_setup_result", process_setup_result)
workflow.add_node("loop_analysis", loop_analysis)
workflow.add_node("tools", ToolNode([get_portfolio_stocks, resolve_ticker, analyze_stock_info]))

workflow.set_entry_point("plan_analysis")

# 1. Plan -> Tools (툴 호출 시)
workflow.add_conditional_edges("plan_analysis", route_main, {"tools": "tools", END: END})

# 2. Tools -> (분기) -> SetupResult 또는 LoopAnalysis
# ✅ 여기가 수정됨: 무조건 loop_analysis가 아니라 조건부 이동
workflow.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "process_setup_result": "process_setup_result",
        "loop_analysis": "loop_analysis"
    }
)

# 3. SetupResult -> LoopAnalysis (셋업 끝났으니 분석 시작)
workflow.add_edge("process_setup_result", "loop_analysis")

# 4. LoopAnalysis -> (분기) -> Tools 또는 END
workflow.add_conditional_edges(
    "loop_analysis",
    route_after_loop,
    {
        "tools": "tools",
        "loop_analysis": "loop_analysis",
        END: END
    }
)

info_analysis_graph = workflow.compile()