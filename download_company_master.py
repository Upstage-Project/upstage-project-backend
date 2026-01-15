"""
DART API에서 회사 마스터 데이터를 다운로드하여 company_master.json 파일을 생성합니다.
"""
import os
from dotenv import load_dotenv
from app.agents.ticker_resolver import TickerResolver

# .env 파일 로드
load_dotenv()

# TickerResolver 인스턴스 생성
resolver = TickerResolver()

# 데이터 로드 (company_master.json이 없으면 자동으로 다운로드)
print("Loading company master data...")
resolver.ensure_loaded()

print(f"\n✅ Company master data loaded successfully!")
print(f"📁 File location: {resolver.data_path}")
print(f"📊 Total companies: {len(resolver.company_list)}")

# 삼성전자 테스트
test_result = resolver.resolve("삼성전자")
print(f"\n🧪 Test: 삼성전자 resolution")
print(f"   Status: {test_result.get('status')}")
print(f"   Company: {test_result.get('company_name')}")
print(f"   Ticker: {test_result.get('ticker')}")
print(f"   Corp Code: {test_result.get('corp_code')}")
