# scripts/seed_stocks.py
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 1) 환경변수로 DATABASE_URL 쓰는 걸 추천
# 예: postgresql+psycopg2://postgres:postgres@localhost:5432/app_db
import os
DATABASE_URL = os.environ.get("DATABASE_URL")

def main():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 환경변수를 설정해줘. 예) postgresql+psycopg2://...")

    # JSON 파일 경로 (프로젝트 루트 기준)
    json_path = Path("DomesticStocks.json")
    if not json_path.exists():
        raise FileNotFoundError(
            "DomesticStocks.json 파일을 프로젝트 루트에 두고 다시 실행해줘."
        )

    data = json.loads(json_path.read_text(encoding="utf-8"))

    engine = create_engine(DATABASE_URL, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    insert_sql = text("""
        INSERT INTO stocks (stock_id, stock_name)
        VALUES (:stock_id, :stock_name)
        ON CONFLICT (stock_id) DO UPDATE
        SET stock_name = EXCLUDED.stock_name
    """)

    with SessionLocal() as db:
        cnt = 0
        for row in data:
            stock_id = str(row.get("Code", "")).strip()
            stock_name = str(row.get("Name", "")).strip()
            if not stock_id or not stock_name:
                continue

            db.execute(insert_sql, {"stock_id": stock_id, "stock_name": stock_name})
            cnt += 1

        db.commit()

    print(f"✅ 업로드 완료: {cnt}개 반영")

if __name__ == "__main__":
    main()
