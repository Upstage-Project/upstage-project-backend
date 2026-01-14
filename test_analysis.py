# test_analysis.py

import asyncio
import os
import json
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# ✅ 작성하신 그래프를 임포트
from app.agents.subgraphs.info_analysis import info_analysis_graph

load_dotenv()


# ---------------------------------------------------------
# 1. Mocking Services (가짜 DB 및 Resolver)
# ---------------------------------------------------------
class MockVectorService:
    def search(self, query, n_results=5):
        # 쿼리가 너무 길면 잘라서 출력
        q_preview = query[:30] + "..." if len(query) > 30 else query
        print(f"    [MockDB] 🔎 검색 중: {q_preview}")

        if "삼성전자" in query:
            return [
                Document(page_content="삼성전자 3분기 영업이익 10조원 회복 전망. HBM3E 공급 가시화.",
                         metadata={"source": "경제신문", "date": "2025-10-01"}),
                Document(page_content="갤럭시 S24 판매 호조로 모바일 부문 실적 개선.", metadata={"source": "IT뉴스", "date": "2025-10-05"})
            ]
        elif "카카오" in query:
            return [Document(page_content="카카오, 경영 쇄신안 발표했으나 사법 리스크 여전.",
                             metadata={"source": "금융뉴스", "date": "2025-10-02"})]
        return []


class MockTickerResolver:
    def ensure_loaded(self): pass

    def resolve(self, query):
        print(f"    [MockResolver] ✅ 종목 확인: {query}")
        return {
            "status": "success",
            "company_name": "삼성전자",
            "stock_code": "005930",
            "corp_code": "00126380"
        }


# ---------------------------------------------------------
# 2. Main Test Loop
# ---------------------------------------------------------
async def main():
    print("\n🚀 InfoAnalysisAgent 정밀 테스트 시작...\n")

    if not os.getenv("UPSTAGE_API_KEY"):
        print("❌ [오류] UPSTAGE_API_KEY가 없습니다. Solar LLM 호출이 실패할 수 있습니다.\n")

    mock_vector_service = MockVectorService()
    mock_ticker_resolver = MockTickerResolver()

    inputs = {
        "messages": [HumanMessage(content="삼성전자 분석해줘")],
        "user_id": "test_user_01",
        "analysis_data": {},
        "analysis_results": []
    }

    config = {
        "configurable": {
            "vector_service": mock_vector_service,
            "ticker_resolver": mock_ticker_resolver
        }
    }

    print("--- 🔄 에이전트 실행 로그 ---")

    final_state = None

    # stream_mode="values"로 전체 상태를 추적
    async for event in info_analysis_graph.astream(inputs, config=config, stream_mode="values"):
        final_state = event

        if "messages" in event and event["messages"]:
            last_msg = event["messages"][-1]

            # 로그 출력 최소화
            if isinstance(last_msg, ToolMessage):
                print(f"✅ [Tool Done] {last_msg.name}")
            elif isinstance(last_msg, AIMessage):
                if last_msg.tool_calls:
                    print(f"👉 [Agent Call] {last_msg.tool_calls[0]['name']}")
                elif last_msg.content:
                    # JSON 결과가 아닌 중간 메시지만 출력
                    if "JSON" not in last_msg.content[:20]:
                        print(f"🤖 [Agent Msg] {last_msg.content[:50]}...")

    print("\n" + "=" * 50)
    print("📊 테스트 최종 결과 (JSON Output)")
    print("=" * 50)

    if final_state and "messages" in final_state:
        last_msg = final_state["messages"][-1]
        try:
            # JSON 파싱 및 출력
            result_json = json.loads(last_msg.content)
            print(json.dumps(result_json, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print("⚠️ JSON 파싱 실패 (Raw Text):")
            print(last_msg.content)
    else:
        print("❌ 결과를 찾을 수 없습니다.")


if __name__ == "__main__":
    asyncio.run(main())