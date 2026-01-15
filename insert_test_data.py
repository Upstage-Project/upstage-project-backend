"""
테스트 데이터 직접 INSERT
"""
import os
from dotenv import load_dotenv
from sqlalchemy import text
from app.deps import get_db_engine

load_dotenv()

engine = get_db_engine()

print("테스트 데이터 INSERT 시작...")

with engine.begin() as conn:
    # 1. Users - 기존에 있으면 스킵
    print("\n[1] Users 생성...")
    conn.execute(text("""
        INSERT INTO users (id, firebase_uid, email)
        VALUES (1, 'test_firebase_uid_1', 'test1@example.com')
        ON CONFLICT (id) DO NOTHING;
    """))
    
    # 2. Stocks
    print("[2] Stocks 생성...")
    conn.execute(text("""
        INSERT INTO stocks (stock_id, stock_name) VALUES
        ('005930', '삼성전자'),
        ('000660', 'SK하이닉스'),
        ('035420', 'NAVER'),
        ('005380', '현대차'),
        ('051910', 'LG화학'),
        ('035720', '카카오'),
        ('068270', '셀트리온'),
        ('105560', 'KB금융'),
        ('012330', '현대모비스'),
        ('055550', '신한지주')
        ON CONFLICT (stock_id) DO NOTHING;
    """))
    
    # 3. User_Stocks
    print("[3] User_Stocks 생성...")
    conn.execute(text("""
        INSERT INTO user_stocks (user_id, stock_id) VALUES
        (1, '005930'),
        (1, '000660'),
        (1, '035420'),
        (1, '005380'),
        (1, '051910'),
        (1, '035720'),
        (1, '068270'),
        (1, '105560'),
        (1, '012330'),
        (1, '055550')
        ON CONFLICT DO NOTHING;
    """))

print("\n✅ 테스트 데이터 INSERT 완료!")

# 확인
print("\n확인: user_id=1의 포트폴리오")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT us.stock_id, s.stock_name 
        FROM user_stocks us 
        JOIN stocks s ON s.stock_id = us.stock_id 
        WHERE us.user_id = 1
        ORDER BY us.stock_id;
    """))
    rows = list(result)
    print(f"\n총 {len(rows)}개 종목:")
    for row in rows:
        print(f"  [{row.stock_id}] {row.stock_name}")
