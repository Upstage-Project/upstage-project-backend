# app/service/agents/info_collector_service.py

from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.subgraphs.info_collector import info_collect_graph


class InfoCollectorService:
    def run(
        self,
        user_query: str,
        build_logs: Optional[List[BaseMessage]] = None,
        config: Optional[RunnableConfig] = None,
        history: Optional[List[BaseMessage]] = None,
    ) -> Dict[str, Any]:
        """
        InfoCollector 서브그래프 실행 서비스.

        - user_query: 사용자의 원 질문
        - history: 이전 대화 히스토리(있으면 messages에 그대로 붙임)
        - build_logs: 이전 에이전트(또는 상위 오케스트레이터)의 로그/요약(있으면 참고 컨텍스트로 제공)
        - config: Tool 의존성 주입용
          (예: vector_service, ticker_resolver, dart_api_key 등은 config["configurable"] 아래에 들어가야 함)
        """

        # 1) Handoff 메시지 구성
        #    - info_collector.py의 instruction_info_collect에 맞춰, Collector가 해야 할 순서를 명확히 안내
        handoff_msg = (
            f'Original User Query: "{user_query}"\n\n'
            "You are InfoCollectorAgent (InvestmentInfoCollector).\n"
            "Follow this order:\n"
            "1) Resolve the company first if needed (resolve_ticker).\n"
            "2) Search internal KB first (search_invest_kb).\n"
            "3) If insufficient, fetch external info:\n"
            "   - News: search_news\n"
            "   - Financials: get_financial_statement (DART)\n"
            "4) Optionally save useful external summaries (add_to_invest_kb).\n\n"
            "Rules:\n"
            "- Use at most ONE tool call per turn.\n"
            "- Keep evidence (dates/sources) where possible.\n"
        )

        # 2) build_logs가 있으면 "이전 컨텍스트"로 추가
        #    - build_logs[-1].content를 그대로 붙이되, 길면 너무 커질 수 있으니 필요 시 자르는 것도 고려 가능
        if build_logs:
            last_context = build_logs[-1].content if build_logs[-1].content else ""
            handoff_msg += f"\nPrevious context:\n{last_context}"

        # 3) 메시지 구성: history(있으면) + 새 HumanMessage(handoff)
        messages: List[BaseMessage] = []
        if history:
            messages.extend(history)

        messages.append(HumanMessage(content=handoff_msg))

        # 4) 그래프 실행
        #    - info_collect_graph는 state={"messages": [...]} 형태를 기대
        sub_result = info_collect_graph.invoke(
            {"messages": messages},
            config=config,
        )

        # 5) 새로 생성된 AI 메시지만 추출해서 반환
        #    - ToolMessage까지 보고 싶으면 여기에서 isinstance 조건을 확장하면 됨
        history_len = len(messages)
        new_messages = [
            msg
            for msg in sub_result["messages"][history_len:]
            if isinstance(msg, AIMessage)
        ]

        return {
            "extract_logs": new_messages,
            "process_status": "success",
        }
