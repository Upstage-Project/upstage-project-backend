# app/agents/state.py
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# 각 하위 에이전트(Sub-graph)가 사용할 독립적인 State 정의
class InfoCollectorAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class InfoAnalysisAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class AnswerGenAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# 메인 슈퍼 그래프(Super Graph)가 관리할 전체 State 정의
class MainState(TypedDict):
    user_query: str                     # 사용자의 최초 질문
    build_logs: List[BaseMessage]        # 내부 검색(RAG) 로그
    augment_logs: List[BaseMessage]      # 외부 검색(Augment) 로그
    extract_logs: List[BaseMessage]      # 내부 정보 추출(Extract) 로그
    answer_logs: Annotated[List[BaseMessage], add_messages]  # 최종 답변 로그
    process_status: str                 # 현재 처리 상태
    loop_count: int                     # 무한 루프 방지용 카운터
