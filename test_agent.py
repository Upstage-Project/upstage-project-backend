import sys
import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

# 1. 환경변수 로드
load_dotenv()

# 2. 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage
from app.agents.subgraphs.info_collector import info_collect_graph
from app.core.db import engine


# ✅ [Mock] 가짜 Ticker Resolver 클래스 정의
class MockTickerResolver:
    def ensure_loaded(self):
        pass

    def resolve(self, user_input: str) -> Dict[str, Any]:
        # 사용자가 뭘 묻든 "삼성전자" 정보를 반환하도록 설정 (테스트용)
        print(f"   [MockResolver] Resolving: {user_input} -> 삼성전자")
        return {
            "status": "success",
            "company_name": "삼성전자",
            "stock_code": "005930",
            "corp_code": "00126380",  # DART 고유 코드
            "reason": "Mock resolve success"
        }


def run_test():
    print("🚀 에이전트 실행 시작 (단일 기업 모드)...")

    user_id = "u123"
    # "포트폴리오" 단어를 빼고 직접적으로 기업을 물어봅니다.
    query = "삼성전자 최근 뉴스랑 재무제표 조회해서 정리해줘"

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "collected": {},
        "user_id": user_id,
    }

    # ✅ [수정] config에 MockTickerResolver 주입
    config = {
        "configurable": {
            "db_engine": engine,
            "join_stock_master": True,
            "ticker_resolver": MockTickerResolver(),  # <--- 여기가 핵심!
            "dart_api_key": os.getenv("DART_API_KEY"),  # 명시적으로 넣어줌
        },
        # LangGraph 재귀 한도 늘리기 (필요 시)
        "recursion_limit": 50
    }

    try:
        # stream=False 대신 invoke 사용
        result = info_collect_graph.invoke(initial_state, config=config)

        print("\n" + "=" * 50)
        print("✅ 실행 완료! 결과 확인")
        print("=" * 50)

        collected = result.get("collected", {})

        # 1. 에러 로그 확인
        if collected.get("errors"):
            print("\n❌ 발생한 에러:")
            for err in collected["errors"]:
                print(f" - Tool: {err.get('tool')}")
                print(f"   Msg:  {err.get('content')}")

        # 2. 수집된 데이터 확인
        company = collected.get("company")
        if company:
            print(f"\n🏢 식별된 기업: {company.get('company_name')} ({company.get('stock_code')})")

            # 뉴스
            news = collected.get("news", [])
            print(f"\n📰 검색된 뉴스 헤드라인: {len(news)}건")
            for n in news[:3]:
                print(f" - {n.get('title')}")

            # 기사 본문
            articles = collected.get("articles", [])
            print(f"\n📄 크롤링된 기사 본문: {len(articles)}건")
            for a in articles:
                print(f" - [{a.get('status')}] {a.get('title')} (길이: {len(a.get('body') or '')})")

            # 재무제표
            fin = collected.get("financials")
            if fin and fin.get("status") == "success":
                print(f"\n💰 재무제표 ({fin.get('bsns_year')} {fin.get('report_type')}):")
                ka = fin.get("key_accounts", {})
                print(f" - 매출액: {ka.get('revenue')}")
                print(f" - 영업이익: {ka.get('operating_income')}")
                print(f" - 당기순이익: {ka.get('net_income')}")
            else:
                print("\n💰 재무제표: 수집 실패 또는 요청 안함")
        else:
            print("\n⚠️ 기업 식별 실패")

        # 3. KB 저장소 확인
        queue = collected.get("kb_save_queue", [])
        saved = collected.get("kb_saved", [])
        print(f"\n💾 KB 저장 상태: 큐 대기 {len(queue)}건 / 저장 완료 {len(saved)}건")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_test()