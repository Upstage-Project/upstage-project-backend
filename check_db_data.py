"""
DB 데이터 확인 스크립트
"""
import os
from dotenv import load_dotenv
from sqlalchemy import text
from app.deps import get_db_engine

load_dotenv()

engine = get_db_engine()

print("=" * 60)
print("데이터베이스 데이터 확인")
print("=" * 60)

with engine.connect() as conn:
    print("\n[1] Users 테이블:")
    result = conn.execute(text("SELECT id, firebase_uid, email FROM users LIMIT 5;"))
    for row in result:
        print(f"  ID: {row.id}, UID: {row.firebase_uid[:20]}..., Email: {row.email}")
    
    print("\n[2] Stocks 테이블:")
    result = conn.execute(text("SELECT stock_id, stock_name FROM stocks LIMIT 10;"))
    for row in result:
        print(f"  [{row.stock_id}] {row.stock_name}")
    
    print("\n[3] User_Stocks 테이블 (user_id=1):")
    result = conn.execute(text("""
        SELECT us.user_id, us.stock_id, s.stock_name 
        FROM user_stocks us 
        JOIN stocks s ON s.stock_id = us.stock_id 
        WHERE us.user_id = 1;
    """))
    rows = list(result)
    if rows:
        for row in rows:
            print(f"  User {row.user_id}: [{row.stock_id}] {row.stock_name}")
    else:
        print("  ⚠️ user_id=1의 포트폴리오 데이터가 없습니다!")
        print("  test.sql의 INSERT가 실패했거나 user_id가 다릅니다.")

print("\n" + "=" * 60)
