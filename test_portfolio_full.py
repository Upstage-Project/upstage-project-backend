"""
포트폴리오 전체 플로우 통합 테스트
"""
import os
from dotenv import load_dotenv
from app.agents.orchestrator import run_investment_orchestrator

load_dotenv()

print("=" * 60)
print("포트폴리오 질의 통합 테스트")
print("=" * 60)

# user_id=5는 실제 Firebase 사용자 (hijason3596@gmail.com)
# user_id=1은 test.sql의 테스트 사용자

test_queries = [
    ("1", "내 포트폴리오 어때"),
    ("1", "보유 종목 분석해줘"),
]

for user_id, query in test_queries:
    print(f"\n{'='*60}")
    print(f"User ID: {user_id}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    try:
        result = run_investment_orchestrator(
            user_query=query,
            user_id=user_id
        )
        
        final_answer = result.get("final_answer", "")
        collected = result.get("collected_info", {})
        
        print("\n[Collected Info]")
        print(f"  Portfolio Mode: {collected.get('portfolio_mode')}")
        print(f"  Portfolio Holdings: {len(collected.get('portfolio_holdings', []))} items")
        
        holdings = collected.get('portfolio_holdings', [])
        if holdings:
            print("\n  Holdings:")
            for h in holdings[:3]:  # 처음 3개만 출력
                print(f"    - [{h.get('ticker')}] {h.get('name')}")
            if len(holdings) > 3:
                print(f"    ... and {len(holdings) - 3} more")
        
        print(f"\n[Final Answer (first 200 chars)]")
        print(final_answer[:200] + "..." if len(final_answer) > 200 else final_answer)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print("테스트 완료!")
print(f"{'='*60}")
