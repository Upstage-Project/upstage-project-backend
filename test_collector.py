from langchain_core.messages import HumanMessage
import os

# 모듈 경로에 주의하세요 (사용하시는 프로젝트 구조에 맞게 import)
from app.agents.subgraphs.info_collector import info_collect_graph
from app.agents.ticker_resolver import TickerResolver
from app.core.db import engine


# --- Mock VectorService (테스트용) ---
class MockVectorService:
    def add_documents(self, contents, metadatas):
        print(f"\n[Mock VectorDB] Saved {len(contents)} documents.")

    def search(self, query, n_results=5):
        print(f"\n[Mock VectorDB] Searching: {query}")
        return []


def test_info_collector_samsung():
    # 1. API Key 체크 (없으면 경고)
    if not os.getenv("DART_API_KEY"):
        print("⚠️ Warning: DART_API_KEY is missing. Financials might fail.")

    # 2. 초기 State 설정
    state = {
        "messages": [HumanMessage(content="삼성전자 기업 정보 알려줘")],
        "collected": {},
        "user_id": "u-test-1",
    }

    # 3. 의존성 주입 (TickerResolver, MockDB 등)
    # TickerResolver는 내부적으로 company_master.json을 로드합니다.
    ticker_resolver = TickerResolver()

    config = {
        "recursion_limit": 150,
        "configurable": {
            "ticker_resolver": ticker_resolver,
            "db_engine": engine,
            "vector_service": MockVectorService(),  # 테스트용 Mock
            "dart_api_key": os.getenv("DART_API_KEY"),
        }
    }

    print("🚀 Info Collector Agent 시작...\n")

    # 4. 그래프 실행
    result = info_collect_graph.invoke(state, config=config)
    collected = result.get("collected", {})

    # --- 결과 출력 ---
    print("\n" + "=" * 40)
    print("      🧪 테스트 실행 결과 리포트")
    print("=" * 40)

    # 1) 기본 정보
    print(f"\n✅ Query Type: {collected.get('query_type')}")
    print(f"✅ Target Company: {collected.get('company')}")

    # 2) 뉴스 수집 결과
    news = collected.get("news") or []
    articles = collected.get("articles") or []
    print(f"\n✅ 수집된 뉴스 헤드라인: {len(news)}건")
    print(f"✅ 수집된 기사 본문: {len(articles)}건")

    # 3) 재무제표 상세 정보 (여기가 수정된 부분입니다)
    fin = collected.get("financials")
    print("\n✅ 재무제표 데이터 (Financials):")

    if isinstance(fin, dict) and fin.get("status") == "success":
        print(f"   - 기업코드(Corp): {fin.get('corp_code')}")
        print(f"   - 기준년도/분기: {fin.get('bsns_year')}년 {fin.get('report_type')}")

        # 주요 계정 과목 출력
        ka = fin.get("key_accounts", {})

        def fmt_money(val):
            if val is None: return "정보 없음"
            return f"{val:,} 원"

        print("-" * 30)
        print(f"   💰 매출액      : {fmt_money(ka.get('revenue'))}")
        print(f"   💰 영업이익    : {fmt_money(ka.get('operating_income'))}")
        print(f"   💰 당기순이익  : {fmt_money(ka.get('net_income'))}")
        print(f"   🏛️ 자산총계    : {fmt_money(ka.get('total_assets'))}")
        print(f"   🏛️ 부채총계    : {fmt_money(ka.get('total_liabilities'))}")
        print(f"   🏛️ 자본총계    : {fmt_money(ka.get('total_equity'))}")
        print("-" * 30)
    else:
        print(f"   ❌ 재무정보 수집 실패 또는 없음 (Status: {fin.get('status') if isinstance(fin, dict) else fin})")
        if isinstance(fin, dict) and fin.get("message"):
            print(f"   ❌ 원인: {fin.get('message')}")

    # 4) 저장 큐 확인
    print(f"\n✅ VectorDB 저장 완료 문서 수: {len(collected.get('kb_saved', []))} 배치")


if __name__ == "__main__":
    # .env 로드 (필요시)
    from dotenv import load_dotenv

    load_dotenv()

    test_info_collector_samsung()