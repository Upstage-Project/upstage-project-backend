import os
import sys
from dotenv import load_dotenv
from sqlalchemy import text  # [추가] DB 연결 테스트용

# 프로젝트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.orchestrator import run_investment_orchestrator
from app.service.vector_service import VectorService

# [핵심] deps.py에서 DB 엔진 가져오기 추가
from app.deps import (
    get_vector_repository,
    get_embedding_service,
    get_ticker_resolver,
    get_db_engine  # [추가] DB 엔진 의존성
)

load_dotenv()


def run_real_test(user_query: str):
    print("🚀 [Full System Test] 벡터 DB + 포트폴리오 RDB 통합 테스트 시작...\n")

    if not os.getenv("UPSTAGE_API_KEY"):
        print("❌ 오류: UPSTAGE_API_KEY가 없습니다. .env 파일을 확인하세요.")
        return

    try:
        # ---------------------------------------------------------
        # 1. 의존성 객체 생성 (deps.py 함수 활용)
        # ---------------------------------------------------------

        # (1) 레포지토리 & 임베딩
        vector_repo = get_vector_repository()
        embedding_svc = get_embedding_service()

        # (2) Ticker Resolver
        ticker_resolver = get_ticker_resolver()

        # (3) [추가] DB 엔진 로드 및 연결 테스트
        db_engine = get_db_engine()
        print(f"✅ DB Engine 객체 로드 완료")

        # 간단한 SQL 실행으로 실제 연결 확인
        try:
            with db_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ RDB(PostgreSQL) 연결 성공!")
        except Exception as e:
            print(f"❌ RDB 연결 실패: {e}")
            print("   .env 파일의 POSTGRES_SERVER, POSTGRES_USER 등을 확인해주세요.")
            return

        # (4) VectorService 수동 조립
        vector_service = VectorService(
            vector_repository=vector_repo,
            embedding_service=embedding_svc
        )

        # ---------------------------------------------------------
        # 2. 오케스트레이터 설정 (DB 엔진 주입)
        # ---------------------------------------------------------
        config = {
            "recursion_limit": 300,
            "configurable": {
                "vector_service": vector_service,
                "ticker_resolver": ticker_resolver,
                "dart_api_key": os.getenv("DART_API_KEY"),

                # [중요] 여기에 실제 db_engine을 넣어줍니다.
                "db_engine": db_engine,
            }
        }

        print(f"\n💬 질문: {user_query}")
        print("🔄 [Orchestrator] 에이전트 실행 중...")

        result = run_investment_orchestrator(
            user_query=user_query,
            user_id="1",
            config=config
        )

        # ---------------------------------------------------------
        # 3. 결과 출력
        # ---------------------------------------------------------
        print("\n" + "=" * 50)
        print("✅ [Final Answer] 최종 답변 결과")
        print("=" * 50)
        print(result.get("final_answer"))


    except Exception as e:
        print(f"\n❌ 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # [팁] 포트폴리오 DB를 테스트하려면 질문을 바꿔보세요.
    # 예: "내 포트폴리오 구성을 알려줘" 또는 "현재 보유한 삼성전자 수익률은?"

    # query = "삼성전자의 최근 뉴스와 실적을 알려줘" # (기존 질문)
    query = "내 포트폴리오 종목 조사해줘"  # (DB 테스트 질문)

    run_real_test(query)