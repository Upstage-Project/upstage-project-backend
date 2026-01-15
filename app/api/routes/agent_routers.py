from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.logger import logger
from app.models.schemas.agent import (
    ChatRequest,
    ChatResponse,
    TokenStreamEvent,
    LogStreamEvent,
    ErrorStreamEvent
)

# 유저 인증 및 모델 의존성
from app.db.models import User
from app.api.user_deps import get_current_user

# AI 에이전트 관련 임포트 (Orchestrator 직접 호출)
from langchain_core.messages import HumanMessage
from app.agents.orchestrator import orchestrator_graph
from app.agents.orchestrator import run_investment_orchestrator

import json
import asyncio

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/health")
async def health_check():
    """서버가 살아있는지 확인하는 헬스 체크용 엔드포인트입니다."""
    return {"status": "healthy", "message": "Agent service is running"}


# 일반채팅 (결과를 한 번에 기다렸다가 받는 전통적 API)
@router.post("/chat", response_model=ChatResponse)
async def chat(
        request: ChatRequest,
        current_user: User = Depends(get_current_user)
):
    try:
        # 1. 에이전트 실행 (Wrapper 함수 사용)
        # run_investment_orchestrator 내부에서 초기 상태(inputs) 설정 및 그래프 실행(ainvoke)을 수행합니다.
        result = await run_investment_orchestrator(
            user_query=request.query,
            user_id=str(current_user.id)
        )

        # 2. 결과 추출
        final_ans = result.get("final_answer", "")

        # final_answer가 비어있을 경우, 메시지 기록의 마지막 내용 사용 (Fallback)
        if not final_ans:
            messages = result.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    final_ans = last_msg.content
                elif isinstance(last_msg, dict):
                    final_ans = last_msg.get("content", "")
                else:
                    final_ans = str(last_msg)

        return ChatResponse(
            answer=final_ans,
            user_query=request.query,
            process_status="completed",
            loop_count=0
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return ChatResponse(
            answer=f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}",
            user_query=request.query,
            process_status="error",
            loop_count=0
        )


# 스트리밍 채팅 (에이전트의 생각과 답변을 실시간으로 나누어 전송)
# @router.post("/chat/stream")
# async def chat_stream(
#         request: ChatRequest,
#         current_user: User = Depends(get_current_user)
# ):
#     async def event_generator():
#         try:
#             inputs = {
#                 "messages": [HumanMessage(content=request.query)],
#                 "user_id": str(current_user.id),
#                 "collected": {},
#                 "analysis_data": {},
#                 "analysis_results": [],
#                 "final_answer": ""
#             }
#
#             # LangGraph v0.1/v0.2 호환 astream_events 사용
#             # version="v1"은 구버전 호환용 이벤트 스키마를 사용
#             async for event in orchestrator_graph.astream_events(inputs, version="v1"):
#                 kind = event["event"]
#                 name = event["name"]
#
#                 # 1. 단계별 상태 로그 전송 (Log Stream Event)
#                 # orchestrator.py에 정의된 노드 이름: info_collector, info_analysis, answer_gen
#                 if kind == "on_chain_start":
#                     if name == "info_collector":
#                         yield f"data: {LogStreamEvent(log='정보 수집 중...').model_dump_json(ensure_ascii=False)}\n\n"
#                     elif name == "info_analysis":
#                         yield f"data: {LogStreamEvent(log='정보 분석 중...').model_dump_json(ensure_ascii=False)}\n\n"
#                     elif name == "answer_gen":
#                         yield f"data: {LogStreamEvent(log='답변 생성 중...').model_dump_json(ensure_ascii=False)}\n\n"
#
#                 # 2. 답변 토큰 스트리밍 (TokenStreamEvent)
#                 # 'answer_gen' 노드 내부에서 발생하는 LLM 스트리밍 이벤트만 클라이언트에 전송
#                 elif kind == "on_chat_model_stream":
#                     # 메타데이터를 통해 현재 실행 중인 노드가 answer_gen인지 확인
#                     # (참고: orchestrator.py의 subgraph invoke 시 config가 전달되어야 내부 이벤트가 보임)
#                     # 만약 내부 이벤트가 안 보일 경우, 이 부분은 동작하지 않을 수 있으나 로직은 맞음.
#                     metadata = event.get("metadata", {})
#                     # langgraph_node 키는 LangGraph 버전에 따라 다를 수 있으나 일반적으로 사용됨
#                     node = metadata.get("langgraph_node", "")
#
#                     # 혹은 answer_gen 단계에서 실행되는지 추론
#                     if node == "answer_gen" or name == "answer_gen":
#                         data = event.get("data", {})
#                         chunk = data.get("chunk")
#                         if chunk:
#                             content = chunk.content
#                             if content:
#                                 yield f"data: {TokenStreamEvent(answer=content).model_dump_json(ensure_ascii=False)}\n\n"
#
#             yield "data: [DONE]\n\n"
#
#         except Exception as e:
#             logger.error(f"Stream error: {e}")
#             yield f"data: {ErrorStreamEvent(error=str(e)).model_dump_json(ensure_ascii=False)}\n\n"
#
#     return StreamingResponse(event_generator(), media_type="text/event-stream")
#
#
# @router.get("/sync-status")
# async def get_sync_status(
#         current_user: User = Depends(get_current_user)
# ):
#     """(임시) 지식 베이스 통계 등은 별도 서비스 로직이 필요하므로 더미 반환"""
#     return {"status": "success", "message": "Knowledge stats not implemented yet without AgentService"}