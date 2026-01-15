from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, Optional

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


# =========================
# Utils
# =========================
def _ensure_session_id(request: ChatRequest) -> str:
    """
    프론트가 session_id를 안 보내도 백엔드에서 생성해서 유지.
    """
    sid = getattr(request, "session_id", None)
    if sid and isinstance(sid, str) and sid.strip():
        return sid.strip()
    return str(uuid.uuid4())


def _to_json(model_obj: Any) -> str:
    """
    Pydantic v2: model_dump_json()
    Pydantic v1: json()
    """
    dump_json = getattr(model_obj, "model_dump_json", None)
    if callable(dump_json):
        return dump_json(ensure_ascii=False)

    to_json = getattr(model_obj, "json", None)
    if callable(to_json):
        return to_json(ensure_ascii=False)

    # fallback
    import json
    if isinstance(model_obj, dict):
        return json.dumps(model_obj, ensure_ascii=False)
    return json.dumps({"value": str(model_obj)}, ensure_ascii=False)


def _extract_answer(result: Any) -> str:
    """
    agent_service.run_agent 결과에서 최종 answer를 최대한 안전하게 뽑기.
    """
    if isinstance(result, dict):
        # 흔한 최종 키들 커버
        for k in ("answer", "final_answer", "output", "response", "text", "content"):
            v = result.get(k)
            if isinstance(v, str) and v.strip():
                return v

        # 중첩 구조 커버
        for k in ("final", "result", "data"):
            v = result.get(k)
            if isinstance(v, dict):
                for kk in ("answer", "final_answer", "output", "response", "text", "content"):
                    vv = v.get(kk)
                    if isinstance(vv, str) and vv.strip():
                        return vv

        # answer_logs / messages에서 마지막 ai 메시지
        logs = result.get("answer_logs") or result.get("messages") or result.get("logs") or []
        if logs:
            last = logs[-1]
            msg_type = getattr(last, "type", None) or (last.get("type") if isinstance(last, dict) else None)
            msg_content = getattr(last, "content", None) or (last.get("content") if isinstance(last, dict) else None)
            if msg_type in ("ai", "assistant") and isinstance(msg_content, str) and msg_content.strip():
                return msg_content

    if isinstance(result, str) and result.strip():
        return result

    return "응답을 생성하지 못했습니다."


def _make_chat_response(answer: str, sid: str) -> Any:
    """
    ChatResponse 모델에 session_id가 없을 수도 있어 안전하게 반환.
    """
    try:
        # pydantic v2
        fields = getattr(ChatResponse, "model_fields", None)
        if isinstance(fields, dict) and "session_id" in fields:
            return ChatResponse(answer=answer, session_id=sid)

        # pydantic v1
        fields = getattr(ChatResponse, "__fields__", None)
        if isinstance(fields, dict) and "session_id" in fields:
            return ChatResponse(answer=answer, session_id=sid)

        # session_id가 모델에 없으면 dict로
        return {"answer": answer, "session_id": sid}
    except Exception:
        return {"answer": answer, "session_id": sid}


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
            "user_id": getattr(current_user, "id", None),
        }

        # 무한대기 방지 (필요하면 늘려)
        result = await asyncio.wait_for(agent_service.run_agent(inputs, session_id=sid), timeout=60)

        answer = _extract_answer(result)

        logger.info(f"[agent/chat] session_id={sid} user_id={getattr(current_user,'id',None)} answer_len={len(answer)}")
        return _make_chat_response(answer=answer, sid=sid)

    except asyncio.TimeoutError:
        logger.exception("[agent/chat] timeout")
        raise AgentException("chat timeout (60s)")

    except (AgentException, KnowledgeBaseException):
        raise

    except Exception as e:
        logger.exception("[agent/chat] processing failed")
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
        # 시작 이벤트(연결 확인용)
        yield f"data: {_to_json(LogStreamEvent(log=f'stream_start session_id={sid}'))}\n\n"

        try:
            inputs: Dict[str, Any] = {
                "user_query": request.query,
                "process_status": "start",
                "user_id": getattr(current_user, "id", None),
            }

            current_node = ""

            async for event in agent_service.stream_agent(inputs, session_id=sid):
                kind = event.get("event")
                name = event.get("name", "")

                # (디버그가 필요하면 이 줄 주석 해제)
                # logger.info(f"[SSE] event={kind} name={name}")

                # 1) 단계 상태 로그
                if kind == "on_chain_start":
                    if name and ("workflow" in name or name == "super_graph"):
                        current_node = name

                    if name == "info_extract_agent_workflow":
                        yield f"data: {_to_json(LogStreamEvent(log='내부 지식 검색 중...'))}\n\n"
                    elif name == "Knowledge_augment_workflow":
                        yield f"data: {_to_json(LogStreamEvent(log='외부 지식 검색 중(News Search)...'))}\n\n"
                    elif name == "answer_gen_agent_workflow":
                        yield f"data: {_to_json(LogStreamEvent(log='답변 생성 중...'))}\n\n"

                # 2) 도구 사용 로그
                elif kind == "on_tool_start":
                    tool_name = event.get("name")
                    if tool_name == "search_":
                        yield f"data: {_to_json(LogStreamEvent(log='내부 DB 검색 실행...'))}\n\n"
                    elif tool_name == "NEWS":
                        yield f"data: {_to_json(LogStreamEvent(log='News 검색 중...'))}\n\n"

                # 3) 모델 토큰 스트리밍
                elif kind == "on_chat_model_stream":
                    data = event.get("data") or {}
                    chunk = data.get("chunk")

                    content = getattr(chunk, "content", None)
                    if content is None and isinstance(chunk, dict):
                        content = chunk.get("content")

                    # ✅ 토큰이 오면 무조건 보냄 (필터링 때문에 답변이 0이 되는 문제 방지)
                    if content:
                        yield f"data: {_to_json(TokenStreamEvent(answer=str(content)))}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception(f"[agent/stream] error: {e}")
            yield f"data: {_to_json(ErrorStreamEvent(error=str(e)))}\n\n"
            yield "data: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# =========================
# 투자 분석 (Orchestrator 직접 사용)
# =========================
@router.post("/invest")
async def run_invest(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """투자 분석 오케스트레이터를 직접 실행하는 엔드포인트"""
    from app.agents.orchestrator import run_investment_orchestrator
    from app.deps import get_ticker_resolver, get_vector_service, get_db_engine
    
    sid = _ensure_session_id(request)
    
    try:
        # Config 구성
        config = {
            "configurable": {
                "ticker_resolver": get_ticker_resolver(),
                "vector_service": get_vector_service(),
                "db_engine": get_db_engine(),
                "DART_API_KEY": os.getenv("DART_API_KEY"),
            }
        }
        
        user_id = getattr(current_user, "id", None)
        
        result = run_investment_orchestrator(
            user_query=request.query,
            user_id=str(user_id) if user_id else "unknown",
            config=config
        )
        
        answer = result.get("final_answer") or _extract_answer(result)
        
        logger.info(f"[agent/invest] session_id={sid} user_id={user_id} answer_len={len(answer)}")
        return _make_chat_response(answer=answer, sid=sid)
        
    except Exception as e:
        logger.exception("[agent/invest] processing failed")
        raise AgentException(f"invest processing failed: {str(e)}")


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
