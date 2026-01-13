# app/service/agents/info_collector_service.py

from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.subgraphs.info_collector import info_collect_graph


class InfoCollectorService:
    def run(
        self,
        user_query: str,
        user_id: Optional[str] = None,  # ✅ 추가
        build_logs: Optional[List[BaseMessage]] = None,
        config: Optional[RunnableConfig] = None,
        history: Optional[List[BaseMessage]] = None,
    ) -> Dict[str, Any]:
        """
        InfoCollector 서브그래프 실행 서비스.
        - config["configurable"]로 tool 의존성 주입 (vector_service, ticker_resolver, db_engine, dart_api_key 등)
        """

        # ✅ 실제 그래프/tools 기능과 일치하도록 정리 (search_invest_kb 언급 제거)
        handoff_msg = (
            f'Original User Query: "{user_query}"\n\n'
            "You are InfoCollectorAgent (InvestmentInfoCollector).\n"
            "Follow this order:\n"
            "1) If portfolio-related, load portfolio stocks first (get_portfolio_stocks).\n"
            "2) Resolve the company if needed (resolve_ticker).\n"
            "3) Fetch external info:\n"
            "   - News: search_news → extract_urls → fetch_article\n"
            "   - Financials: get_financial_statement (DART) if requested\n"
            "4) Save useful snippets/articles/financials to KB (add_many_to_invest_kb).\n\n"
            "Rules:\n"
            "- Use at most ONE tool call per turn.\n"
        )

        if build_logs:
            last_context = build_logs[-1].content if build_logs[-1].content else ""
            handoff_msg += f"\nPrevious context:\n{last_context}"

        messages: List[BaseMessage] = []
        if history:
            messages.extend(history)

        messages.append(HumanMessage(content=handoff_msg))

        # ✅ state에 user_id 넣기 (포트폴리오 질문이면 필수)
        state: Dict[str, Any] = {"messages": messages}
        if user_id:
            state["user_id"] = user_id

        sub_result = info_collect_graph.invoke(
            state,
            config=config,
        )

        history_len = len(messages)
        new_messages = [
            msg
            for msg in sub_result["messages"][history_len:]
            if isinstance(msg, AIMessage)
        ]

        return {
            "extract_logs": new_messages,
            "process_status": "success",
            "collected": sub_result.get("collected"),
        }
