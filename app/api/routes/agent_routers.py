from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
"""78페이지 지식 관리가 따로 필요하면 추가
    AddKnowledgeRequest,
    KnowledgeResponse,
    NewsArticle,
    FinancialStatement"""
from app.core.logger import logger
from app.models import (
    ChatRequest,
    ChatResponse,
    TokenStreamEvent,
    LogStreamEvent,
    ErrorStreamEvent
)

from app.exceptions imprt AgentException, KnowledgeBaseException
from app.deps import get_agent_service
from app.service.agent_service import AgentService

# 라우터 설정: 아래 모든 @router.
router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/health")
async def health_check():
    """서버가 살아있는지 확인하는 헬스 체크용 엔드포인트입니다."""
    return {"status": "healthy", "message": "Agent service is running"}


# 일반채팅 (결과를 한 번에 기다렸다가 받는 전통적 API)
@router.post("/chat", response_model=ChatResponse)
async def chat(
        request: ChatRequest, agent_service: AgentService=Depends(get_agent_service)
):
    try:
        # 1. 에이전트 실행 (결과가 나올 때까지 기다림)
        inputs = {"user_query": request.query, "process_status": "start"}
        result = agent_service.run_agent(inputs, session_id=request.session_id)

        # 2. 결과 처리
        serializable_result = {"answer": ""}

        # 대화 기록 중 마지막 AI 메시지를 찾아 최종 답변으로 설정
        answer_logs = result.get("asnwer_logs", [])
        if answer_logs:
            last_msg = answer_logs[-1]
            if getattr(last_msg, 'type', '' == 'ai')
                serializable_result["answer"] = last_msg.content

        # 메타데이터(상태, 루프 횟수 등) 추가
        for k in ["user_query", "process_status", "loop_count"]:
            if k in result:
                serializable_result[k] = result[k]

        return serializable_result

    # 커스텀 예외 처리
    except (AgentException, KnowledgeBaseException) as e:
        raise e
    excep Exception as e:
    raise AgentException(f"chat processing failed: {str{e}}")

# 스트리밍 채팅 (에이전트의 생각과 답변을 실시간으로 나누어 전송한다)

@router.post("/chat/stream")
async def chat_stream(
        request: chatRequest, agent_service: AgentService =
        Depends(get_agent_service)
):
    async def event_generator():
        try:
            inputs = {"user_query": request.query, "process_status": "start"}
            current_node = "" # 현재 에이전트가 어떤 작업을 하고 있는지 추적

            # LangGraph의 이벤트를 실시간으로 하나씩 받아서 처리
            async for event in agent_service.stream_agent(inputs,
                                                          session_id=request.session_id):
                kind = event.get("event")
                name = event.get("name", "")

                # 1. 단계별 상태 로그 전송 (Log Stream Event)
                # Wrokflow 노드에 진입할 때마다 '검색 중...'. '답변 생성 중...' 등의 로그를 보냅니다

                if kind == "on_chain_start":
                    if name and ("workflow" in name or name == "super_graph"):
                        current_node = name # 현재 단계 업데이트

                    if name == "info_extract_agent_workflow":
                        yield f"data: {LogStreamEvent(log='내부 지식 검색 중...')
                        .model_dump_json(ensure_ascii=False)}\n\n"
                    elif name == "Knowledge_augment_workflow":
                        yield f"data: {LogStreamEvent(log='외부 지식 검색 중'
                                                          '(News Search)...')
                        .model_dump_json(ensure_ascii=False)}\n\n"
                    elif name == "answer_gen_agent_workflow":
                        yield f"data: {LogStreamEvent(log='답변 생성 중...')
                        .model_dump_json(ensure_ascii=False)}\n\n"

                # 2. 도구 사용 로그 전송
                elif kind == 'on_tool_start':
                    if event.get("name") == "search_" # 여기에 벡터 DB 조회하는 tool 메서드
                        from app.models import LogStreamEvent
                        yield f"data: {LogStreamEvent(log='내부 DB 검색 실행...')
                        .model_dump_json(ensure_ascii=False)}\n\n"
                    elif event.get("name") == "NEWS" # 뉴스 API 조회
                        yield f"data: {LogStreamEvent(log='News 검색 충...')
                        .model_dump_json(ensure_ascii=False)}\n\n"

                # 3. 답변 토큰 스트리밍 (TokenStreamEvent)
                elif kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        # [중요 로직] 검색이나 추출 단계에서의 LLM 출력은 사용자에게 보여주지 않고(숨김),
                        # 최종 답변 생성 단계 ('answer_gen')일 때만 토큰 전송
                        if current_node not in ["info_extract_agent_workflow",
                                                "Knowledge_augment_workflow"]:
                            yield f"data: {TokenStreamEvent(answer=content).model_dump_json(ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n" # 종료 신호

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data:\
            {ErrorStreamEvent(error=str(e)).model_dump_json(ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# app/api/route/agent_routers.py (단순화 버전)
@router.get("/sync-status")
async def get_sync_status(agent_service: AgentService = Depends(get_agent_service)):
    """현재 지식 베이스에 뉴스가 얼마나 쌓였는지 확인하는 API"""
    return agent_service.get_knowledge_stats()
