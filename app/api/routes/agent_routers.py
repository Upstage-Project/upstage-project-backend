# # app/api/routes/agent_routers.py
# from fastapi import APIRouter, Depends
# from fastapi.responses import StreamingResponse
# from app.core.logger import logger
# from app.models import (
#     ChatRequest,
#     ChatResponse,
#     TokenStreamEvent,
#     LogStreamEvent,
#     ErrorStreamEvent
# )
#
#
# from app.exceptions import AgentException, KnowledgeBaseException
# from app.deps import get_agent_service
# from app.service.agent_service import AgentService
#
# router = APIRouter(prefix="/agent", tags=["agent"])
#
# @router.get("/health")
# async def health_check():
#     """서버가 살아있는지 확인하는 헬스 체크용 엔드포인트입니다."""
#     return {"status": "healthy", "message": "Agent service is running"}
#
#
# # 일반채팅 (결과를 한 번에 기다렸다가 받는 전통적 API)
# @router.post("/chat", response_model=ChatResponse)
# async def chat(
#         request: ChatRequest, agent_service: AgentService = Depends(get_agent_service)
# ):
#     try:
#         # 1. 에이전트 실행 (결과가 나올 때까지 기다림)
#         inputs = {"user_query": request.query, "process_status": "start"}
#         result = await agent_service.run_agent(inputs, session_id=request.session_id) # async 함수라면 await 필요 가능성 있음
#
#         # 2. 결과 처리
#         serializable_result = {"answer": ""}
#
#         # 대화 기록 중 마지막 AI 메시지를 찾아 최종 답변으로 설정
#         answer_logs = result.get("answer_logs", []) # asnwer_logs 오타 수정 가능성 고려
#         if answer_logs:
#             last_msg = answer_logs[-1]
#             # [수정] 괄호 위치 및 조건식 수정
#             if getattr(last_msg, 'type', '') == 'ai':
#                 serializable_result["answer"] = last_msg.content
#
#         # 메타데이터(상태, 루프 횟수 등) 추가
#         for k in ["user_query", "process_status", "loop_count"]:
#             if k in result:
#                 serializable_result[k] = result[k]
#
#         return serializable_result
#
#     # 커스텀 예외 처리
#     except (AgentException, KnowledgeBaseException) as e:
#         raise e
#     # [수정] excep -> except, str{e} -> str(e)
#     except Exception as e:
#         raise AgentException(f"chat processing failed: {str(e)}")
#
#
# # 스트리밍 채팅 (에이전트의 생각과 답변을 실시간으로 나누어 전송한다)
# @router.post("/chat/stream")
# async def chat_stream(
#         # [수정] chatRequest -> ChatRequest
#         request: ChatRequest, agent_service: AgentService = Depends(get_agent_service)
# ):
#     async def event_generator():
#         try:
#             inputs = {"user_query": request.query, "process_status": "start"}
#             current_node = "" # 현재 에이전트가 어떤 작업을 하고 있는지 추적
#
#             # LangGraph의 이벤트를 실시간으로 하나씩 받아서 처리
#             async for event in agent_service.stream_agent(inputs, session_id=request.session_id):
#                 kind = event.get("event")
#                 name = event.get("name", "")
#
#                 # 1. 단계별 상태 로그 전송 (Log Stream Event)
#                 if kind == "on_chain_start":
#                     if name and ("workflow" in name or name == "super_graph"):
#                         current_node = name # 현재 단계 업데이트
#
#                     if name == "info_extract_agent_workflow":
#                         yield f"data: {LogStreamEvent(log='내부 지식 검색 중...').model_dump_json(ensure_ascii=False)}\n\n"
#                     elif name == "Knowledge_augment_workflow":
#                         yield f"data: {LogStreamEvent(log='외부 지식 검색 중(News Search)...').model_dump_json(ensure_ascii=False)}\n\n"
#                     elif name == "answer_gen_agent_workflow":
#                         yield f"data: {LogStreamEvent(log='답변 생성 중...').model_dump_json(ensure_ascii=False)}\n\n"
#
#                 # 2. 도구 사용 로그 전송
#                 elif kind == 'on_tool_start':
#                     # [수정] 콜론(:) 추가
#                     if event.get("name") == "search_":
#                         yield f"data: {LogStreamEvent(log='내부 DB 검색 실행...').model_dump_json(ensure_ascii=False)}\n\n"
#                     # [수정] 콜론(:) 추가
#                     elif event.get("name") == "NEWS":
#                         yield f"data: {LogStreamEvent(log='News 검색 중...').model_dump_json(ensure_ascii=False)}\n\n"
#
#                 # 3. 답변 토큰 스트리밍 (TokenStreamEvent)
#                 elif kind == "on_chat_model_stream":
#                     # data 키가 없는 경우 방어 로직 추가
#                     if "data" in event and "chunk" in event["data"]:
#                         content = event["data"]["chunk"].content
#                         if content:
#                             # [중요 로직] 검색이나 추출 단계에서의 LLM 출력은 사용자에게 보여주지 않고,
#                             # 최종 답변 생성 단계 ('answer_gen')일 때만 토큰 전송
#                             # (참고: current_node 조건이 정확한지 확인 필요)
#                             if current_node not in ["info_extract_agent_workflow", "Knowledge_augment_workflow"]:
#                                 yield f"data: {TokenStreamEvent(answer=content).model_dump_json(ensure_ascii=False)}\n\n"
#
#             yield "data: [DONE]\n\n" # 종료 신호
#
#         except Exception as e:
#             logger.error(f"Stream error: {e}")
#             yield f"data: {ErrorStreamEvent(error=str(e)).model_dump_json(ensure_ascii=False)}\n\n"
#
#     return StreamingResponse(event_generator(), media_type="text/event-stream")
#
#
# @router.get("/sync-status")
# async def get_sync_status(agent_service: AgentService = Depends(get_agent_service)):
#     """현재 지식 베이스에 뉴스가 얼마나 쌓였는지 확인하는 API"""
#     return agent_service.get_knowledge_stats()