# app/service/agent_service.py

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional
from app.core.logger import logger


class AgentService:
    """
    LangGraph/orchestrator_graph 없이 동작하는 최소 AgentService.
    - /agent/chat: 즉시 answer 반환
    - /agent/chat/stream: SSE 토큰 스트림 반환(간단히 글자 단위)
    """

    def __init__(self) -> None:
        logger.info("[AgentService] initialized (NO GRAPH)")

    async def run_agent(self, inputs: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        user_query = inputs.get("user_query", "")
        user_id = inputs.get("user_id")

        logger.info(f"[AgentService] run_agent session_id={session_id} user_id={user_id} query={user_query!r}")

        # ✅ 여기서부터 “진짜 로직” 넣으면 됨.
        # 지금은 안정적으로 동작하는 기본 응답만.
        answer = f"요청 확인: {user_query}"

        return {
            "answer": answer,
            "user_query": user_query,
            "process_status": "done",
            "session_id": session_id,
            "user_id": user_id,
        }

    async def stream_agent(
        self, inputs: Dict[str, Any], session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_query = inputs.get("user_query", "")
        user_id = inputs.get("user_id")

        logger.info(f"[AgentService] stream_agent session_id={session_id} user_id={user_id} query={user_query!r}")

        # 라우터가 기대하는 이벤트 형태로 맞춰줌
        yield {"event": "on_chain_start", "name": "answer_gen_agent_workflow"}

        text = f"요청 확인: {user_query}"
        for ch in text:
            class _Chunk:
                def __init__(self, content: str) -> None:
                    self.content = content

            yield {"event": "on_chat_model_stream", "name": "no_graph_stub", "data": {"chunk": _Chunk(ch)}}

    def get_knowledge_stats(self) -> Dict[str, Any]:
        return {"status": "ok"}
