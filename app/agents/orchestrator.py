from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# 각 에이전트 그래프 임포트
try:
    from app.agents.subgraphs.info_collector import info_collect_graph
    from app.agents.subgraphs.info_analysis import info_analysis_graph
    from app.agents.subgraphs.answer_gen import answer_gen_graph
except ImportError:
    pass


# ------------------------------------------------------------------
# 1. 통합 상태 정의 (Orchestrator State)
# ------------------------------------------------------------------
class OrchestratorState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    collected: Dict[str, Any]
    analysis_data: Dict[str, Any]
    analysis_results: List[Dict[str, Any]]
    final_answer: str


# ------------------------------------------------------------------
# 2. 노드 정의 (Nodes)
# ------------------------------------------------------------------
def run_collector(state: OrchestratorState):
    print("\n>>> [Orchestrator] Starting Info Collector...")
    result = info_collect_graph.invoke({
        "messages": state["messages"],
        "user_id": state["user_id"],
        "collected": state.get("collected", {})
    })
    return {
        "collected": result.get("collected", {}),
        "messages": result.get("messages", [])
    }


def run_analyst(state: OrchestratorState):
    print("\n>>> [Orchestrator] Starting Info Analysis...")
    
    # collected 정보를 info_analysis로 전달
    collected = state.get("collected", {})
    
    result = info_analysis_graph.invoke({
        "messages": state["messages"],
        "user_id": state["user_id"],
        "analysis_data": state.get("analysis_data", {}),
        "analysis_results": state.get("analysis_results", []),
        "collected": collected  # 포트폴리오 정보 전달
    })
    return {
        "analysis_data": result.get("analysis_data", {}),
        "analysis_results": result.get("analysis_results", []),
        "messages": result.get("messages", [])
    }


def run_answer_gen(state: OrchestratorState):
    print("\n>>> [Orchestrator] Starting Answer Generation...")
    result = answer_gen_graph.invoke({
        "messages": state["messages"],
        "collected": state.get("collected", {}),
        "analysis_results": state.get("analysis_results", []),
    })

    # [수정된 부분]
    # State 키에 의존하지 않고, 메시지 기록의 '마지막 대화'를 강제로 꺼내옵니다.
    # 이것이 가장 확실한 방법입니다.
    messages = result.get("messages", [])
    final_ans = ""

    if messages:
        last_msg = messages[-1]
        # 1. 객체인 경우 (.content 속성)
        if hasattr(last_msg, "content"):
            final_ans = last_msg.content
        # 2. 딕셔너리인 경우 (가끔 직렬화되면 dict로 올 수 있음)
        elif isinstance(last_msg, dict):
            final_ans = last_msg.get("content", "")
        # 3. 문자열인 경우
        elif isinstance(last_msg, str):
            final_ans = last_msg

    return {
        "final_answer": final_ans,
        "messages": messages
    }


# ------------------------------------------------------------------
# 3. 그래프 구성 (Graph Construction)
# ------------------------------------------------------------------
workflow = StateGraph(OrchestratorState)

workflow.add_node("info_collector", run_collector)
workflow.add_node("info_analysis", run_analyst)
workflow.add_node("answer_gen", run_answer_gen)

workflow.add_edge(START, "info_collector")
workflow.add_edge("info_collector", "info_analysis")
workflow.add_edge("info_analysis", "answer_gen")
workflow.add_edge("answer_gen", END)

orchestrator_graph = workflow.compile()


# ------------------------------------------------------------------
# 4. 실행 헬퍼 함수
# ------------------------------------------------------------------
def run_investment_orchestrator(user_query: str, user_id: str, config=None):
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "user_id": user_id,
        "collected": {},
        "analysis_data": {},
        "analysis_results": [],
        "final_answer": ""
    }

    result = orchestrator_graph.invoke(initial_state, config=config)

    return {
        "final_answer": result.get("final_answer"),
        "analysis_results": result.get("analysis_results"),
        "collected_info": result.get("collected"),
        "history": result.get("messages")
    }