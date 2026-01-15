# app/service/agent_service.py
from __future__ import annotations

import os
import asyncio
from typing import Any, AsyncGenerator, Dict, Optional, Callable

from app.core.logger import logger


class AgentService:
    """
    기존에 만들어둔 agent/orchestrator를 호출하도록 연결한 AgentService.

    - /agent/chat: 최종 answer 반환
    - /agent/chat/stream: SSE 형태로 토큰 스트리밍 (에이전트가 자체 스트림을 안 주면 최종 답을 글자 단위로 흘림)
    """

    def __init__(self) -> None:
        logger.info("[AgentService] initialized (NO GRAPH)")

        # ✅ 네가 만들어 둔 orchestrator(에이전트 엔트리포인트) 연결
        self._runner: Optional[Callable[..., Any]] = None

        try:
            # 너 zip에 존재: app/agents/orchestrator.py
            # 거기 안에 run_investment_orchestrator()가 있음
            from app.agents.orchestrator import run_investment_orchestrator  # type: ignore

            self._runner = run_investment_orchestrator
            logger.info("[AgentService] orchestrator runner loaded: run_investment_orchestrator")
        except Exception as e:
            # import/문법/의존성 문제 등 뭐든 여기로 떨어질 수 있음
            self._runner = None
            logger.exception(f"[AgentService] failed to load orchestrator runner: {e}")

    def _build_config(self) -> Dict[str, Any]:
        """
        오케스트레이터에 전달할 config 구성.
        ticker_resolver, vector_service, db_engine 등 모든 의존성 주입.
        """
        from app.deps import (
            get_ticker_resolver,
            get_vector_service,
            get_db_engine,
        )

        return {
            "recursion_limit": 300,
            "configurable": {
                "ticker_resolver": get_ticker_resolver(),
                "vector_service": get_vector_service(),
                "db_engine": get_db_engine(),
                "dart_api_key": os.getenv("DART_API_KEY"),
            }
        }

    async def run_agent(self, inputs: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        user_query = inputs.get("user_query", "")
        user_id = inputs.get("user_id")

        logger.info(f"[AgentService] run_agent session_id={session_id} user_id={user_id} query={user_query!r}")

        # ✅ 1) 기존 에이전트가 연결되어 있으면 그걸로 “진짜 답” 생성
        if self._runner is not None:
            try:
                # config 빌드 (ticker_resolver 등 의존성 주입)
                config = self._build_config()

                # runner가 동기 함수일 가능성이 높아서 thread로 실행
                result = await asyncio.to_thread(
                    self._runner,
                    user_query=user_query,
                    user_id=str(user_id),
                    config=config
                )

                # 예상 반환 형태:
                # {
                #   "final_answer": "...",
                #   "analysis_results": ...,
                #   "collected_info": ...,
                #   "history": ...
                # }
                answer = (result or {}).get("final_answer") or ""
                if not answer:
                    # 혹시 다른 키로 내려오면 여기서 보정
                    answer = (result or {}).get("answer") or ""

                # 그래도 비면 fallback
                if not answer:
                    answer = f"(에이전트 결과는 왔지만 final_answer가 비어있음) query={user_query}"

                return {
                    "answer": answer,
                    "user_query": user_query,
                    "process_status": "done",
                    "session_id": session_id,
                    "user_id": user_id,
                    # 필요하면 프론트 디버그용으로 추가:
                    # "agent_result": result,
                }
            except Exception as e:
                logger.exception(f"[AgentService] orchestrator run failed: {e}")
                # 아래 fallback으로 내려감

        # ✅ 2) 에이전트 연결 실패/실행 실패 시: 최소 fallback
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

        # 라우터가 기대하는 이벤트 형태
        yield {"event": "on_chain_start", "name": "answer_gen_agent_workflow"}

        # ✅ 에이전트가 “자체 스트림”을 제공하지 않는다고 가정하고,
        # run_agent로 최종 답을 만든 다음 토큰 스트리밍처럼 흘려줌
        result = await self.run_agent(inputs, session_id=session_id)
        text = result.get("answer", "")

        for ch in text:
            class _Chunk:
                def __init__(self, content: str) -> None:
                    self.content = content

            yield {"event": "on_chat_model_stream", "name": "agent_runner", "data": {"chunk": _Chunk(ch)}}

    def get_knowledge_stats(self) -> Dict[str, Any]:
        return {"status": "ok"}
