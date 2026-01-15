from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.logger import logger
from app.models import (
    ChatRequest,
    ChatResponse,
    TokenStreamEvent,
    LogStreamEvent,
    ErrorStreamEvent,
)
from app.exceptions import AgentException, KnowledgeBaseException
from app.deps import get_agent_service
from app.service.agent_service import AgentService

# 유저 인증 의존성
from app.db.models import User
from app.api.user_deps import get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])


def _ensure_session_id(request: ChatRequest) -> str:
    """
    프론트가 session_id를 안 보내도 백엔드에서 생성해서 유지.
    """
    sid = getattr(request, "session_id", None)
    if sid and isinstance(sid, str) and sid.strip():
        return sid.strip()
    return str(uuid.uuid4())


def _extract_answer(result: Any) -> str:
    """
    agent_service.run_agent 결과에서 최종 answer를 최대한 안전하게 뽑기.
    """
    answer = ""

    # 1) dict 형태로 answer 키가 있으면 우선 사용
    if isinstance(result, dict):
        if isinstance(result.get("answer"), str):
            return result["answer"]

        # 2) answer_logs 마지막 ai 메시지 시도
        answer_logs = result.get("answer_logs", [])
        if answer_logs:
            last_msg = answer_logs[-1]
            msg_type = getattr(last_msg, "type", None) or (
                last_msg.get("type") if isinstance(last_msg, dict) else None
            )
            msg_content = getattr(last_msg, "content", None) or (
                last_msg.get("content") if isinstance(last_msg, dict) else None
            )
            if msg_type == "ai" and isinstance(msg_content, str):
                return msg_content

    # 3) 문자열로 바로 온 경우
    if isinstance(result, str):
        return result

    if not answer:
        answer = "응답을 생성하지 못했습니다."

    return answer


# =========================
# 일반 채팅 (한 번에 결과 반환)
# =========================
@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_service: AgentService = Depends(get_agent_service),
    current_user: User = Depends(get_current_user),
):
    sid = _ensure_session_id(request)

    try:
        inputs: Dict[str, Any] = {
            "user_query": request.query,
            "process_status": "start",
            "user_id": getattr(current_user, "id", None),  # 필요하면 에이전트에서 활용
        }

        result = await agent_service.run_agent(inputs, session_id=sid)
        answer = _extract_answer(result)

        # ⚠️ ChatResponse에 session_id 필드가 없으면 모델 수정 필요
        return ChatResponse(answer=answer, session_id=sid)

    except (AgentException, KnowledgeBaseException):
        raise
    except Exception as e:
        logger.exception("chat processing failed")
        raise AgentException(f"chat processing failed: {str(e)}")


# =========================
# 스트리밍 채팅 (SSE)
# =========================
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    agent_service: AgentService = Depends(get_agent_service),
    current_user: User = Depends(get_current_user),
):
    sid = _ensure_session_id(request)

    async def event_generator():
        try:
            inputs: Dict[str, Any] = {
                "user_query": request.query,
                "process_status": "start",
                "user_id": getattr(current_user, "id", None),
            }

            current_node = ""

            # (선택) 스트림 시작 시 session_id 먼저 알려주고 싶으면
            # yield f"data: {LogStreamEvent(log=f'session_id={sid}').model_dump_json(ensure_ascii=False)}\n\n"

            async for event in agent_service.stream_agent(inputs, session_id=sid):
                kind = event.get("event")
                name = event.get("name", "")

                # 1) 단계 상태 로그
                if kind == "on_chain_start":
                    if name and ("workflow" in name or name == "super_graph"):
                        current_node = name

                    if name == "info_extract_agent_workflow":
                        yield f"data: {LogStreamEvent(log='내부 지식 검색 중...').model_dump_json(ensure_ascii=False)}\n\n"
                    elif name == "Knowledge_augment_workflow":
                        yield f"data: {LogStreamEvent(log='외부 지식 검색 중(News Search)...').model_dump_json(ensure_ascii=False)}\n\n"
                    elif name == "answer_gen_agent_workflow":
                        yield f"data: {LogStreamEvent(log='답변 생성 중...').model_dump_json(ensure_ascii=False)}\n\n"

                # 2) 도구 사용 로그
                elif kind == "on_tool_start":
                    tool_name = event.get("name")
                    if tool_name == "search_":
                        yield f"data: {LogStreamEvent(log='내부 DB 검색 실행...').model_dump_json(ensure_ascii=False)}\n\n"
                    elif tool_name == "NEWS":
                        yield f"data: {LogStreamEvent(log='News 검색 중...').model_dump_json(ensure_ascii=False)}\n\n"

                # 3) 모델 토큰 스트리밍
                elif kind == "on_chat_model_stream":
                    data = event.get("data") or {}
                    chunk = data.get("chunk")

                    content = getattr(chunk, "content", None)
                    if content:
                        # 단계 필터링(원하면 더 정확히 맞춰서 조정)
                        if current_node not in ["info_extract_agent_workflow", "Knowledge_augment_workflow"]:
                            yield f"data: {TokenStreamEvent(answer=content).model_dump_json(ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception(f"Stream error: {e}")
            yield f"data: {ErrorStreamEvent(error=str(e)).model_dump_json(ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # nginx 같은 프록시가 버퍼링하면 SSE 끊기는 경우가 있어서
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# =========================
# 동기화 상태 확인
# =========================
@router.get("/sync-status")
async def get_sync_status(
    agent_service: AgentService = Depends(get_agent_service),
    current_user: User = Depends(get_current_user),
):
    """현재 지식 베이스에 뉴스가 얼마나 쌓였는지 확인하는 API"""
    return agent_service.get_knowledge_stats()
