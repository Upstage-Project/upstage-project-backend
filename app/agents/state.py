# app/agents/state.py
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# -------------------------
# Sub-graph states
# -------------------------
class InfoCollectorAgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    # ✅ 포트폴리오 모드에서 필요
    user_id: str

    # ✅ 이번 턴에서 수집한 “구조화된 결과”를 담는 컨테이너
    collected: Dict[str, Any]
    # 예:
    # collected = {
    #   "company": {"company_name": "...", "stock_code": "...", "corp_code": "..."},
    #   "news": [{"title":..., "url":..., "published_at":..., "summary":...}, ...],
    #   "articles": [{"url":..., "title":..., "body":..., "publisher":..., "published_at":...}, ...],
    #   "financials": {"bsns_year": 2024, "report_type":"FY", "key_accounts": {...}},
    #   "kb_saved": [{"status":"success", "metadata": {...}}, ...],
    # }


class InfoAnalysisAgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    # ✅ Collector가 넘겨준 데이터를 그대로 받아 분석에 사용
    collected: Dict[str, Any]
    analysis_result: Dict[str, Any]


class AnswerGenAgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    collected: Dict[str, Any]
    analysis_result: Dict[str, Any]


# -------------------------
# Super-graph main state
# -------------------------
class MainState(TypedDict, total=False):
    user_query: str

    # 로그들
    build_logs: List[BaseMessage]
    augment_logs: List[BaseMessage]
    extract_logs: List[BaseMessage]
    answer_logs: Annotated[List[BaseMessage], add_messages]

    process_status: str
    loop_count: int

    # ✅ 서브그래프 사이에서 전달할 “payload”
    collected: Dict[str, Any]
    analysis_result: Dict[str, Any]
