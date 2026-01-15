"""
포트폴리오 질의 분석 테스트
"""
import os
from dotenv import load_dotenv
from app.agents.tools import analyze_invest_query

load_dotenv()

# 테스트 쿼리들
test_queries = [
    "포트폴리오 조회해줘",
    "내 포트폴리오 분석해줘", 
    "보유 종목 알려줘",
    "내 주식 현황 보여줘",
    "내가 가진 주식들 위험도 알려줘",
    "전체 종목 수익률 알려줘",
    "투자 현황 분석해줘",
    "삼성전자 최근 실적 어때?",  # COMPANY로 분류되어야 함
    "NAVER 기업 정보 알려줘",    # COMPANY로 분류되어야 함
]

print("=" * 60)
print("포트폴리오 질의 분석 테스트")
print("=" * 60)

for i, query in enumerate(test_queries, 1):
    print(f"\n[테스트 {i}] 질의: {query}")
    
    # analyze_invest_query 툴은 RunnableConfig를 받지만, 여기서는 빈 dict로 전달
    result = analyze_invest_query.invoke({"user_query": query})
    
    status = result.get("status")
    query_type = result.get("query_type")
    companies = result.get("companies", [])
    
    print(f"  - Status: {status}")
    print(f"  - Query Type: {query_type}")
    
    if query_type == "PORTFOLIO":
        print("  ✅ 포트폴리오로 올바르게 인식됨!")
    elif query_type == "COMPANY":
        print(f"  ✅ 회사 검색으로 올바르게 인식됨!")
        if companies:
            print(f"  - 회사: {companies}")
    else:
        print(f"  ⚠️ OTHER로 분류됨")
    
    if status == "error":
        print(f"  ❌ 에러: {result.get('message')}")

print("\n" + "=" * 60)
print("테스트 완료!")
print("=" * 60)
