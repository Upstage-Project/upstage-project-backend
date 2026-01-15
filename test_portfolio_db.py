"""
포트폴리오 전체 플로우 테스트
"""
import os
from dotenv import load_dotenv
from app.agents.tools import get_portfolio_stocks
from app.deps import get_db_engine

load_dotenv()

print("=" * 60)
print("포트폴리오 조회 테스트 (DB 연결)")
print("=" * 60)

# DB 엔진 가져오기
engine = get_db_engine()

# config 구성
config = {
    "configurable": {
        "db_engine": engine,
        "join_stock_master": True,  # stocks 테이블과 JOIN
    }
}

# 테스트용 user_id = "1" (test.sql에서 생성한 사용자)
test_user_id = "1"

print(f"\n[테스트] user_id={test_user_id}의 포트폴리오 조회")
print("-" * 60)

# get_portfolio_stocks 툴 호출
from langchain_core.runnables import RunnableConfig

result = get_portfolio_stocks.invoke(
    input={"user_id": test_user_id},
    config=RunnableConfig(configurable=config["configurable"])
)

status = result.get("status")
count = result.get("count")
holdings = result.get("holdings", [])
error = result.get("error")

print(f"Status: {status}")
print(f"Count: {count}")

if status == "success":
    print(f"\n✅ 포트폴리오 조회 성공! {count}개 종목 보유 중\n")
    
    if holdings:
        print("보유 종목 목록:")
        print("-" * 60)
        for i, h in enumerate(holdings, 1):
            ticker = h.get("ticker")
            name = h.get("name")
            print(f"  {i}. [{ticker}] {name}")
    else:
        print("⚠️ 보유 종목이 없습니다.")
        print("   test.sql을 실행하여 테스트 데이터를 추가하세요:")
        print("   psql -U postgres -d upstage_project -f test.sql")
else:
    print(f"\n❌ 포트폴리오 조회 실패!")
    print(f"Error: {error}")

print("\n" + "=" * 60)
print("테스트 완료!")
print("=" * 60)
