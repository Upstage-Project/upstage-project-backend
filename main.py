import json
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================
# Router imports
# =========================
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.routes.user_stock import router as user_stock_router
from app.api.routes.agent_routers import router as agent_router

from app.core.firebase import init_firebase

# =========================
# DB & Model Imports (데이터 자동 주입용)
# =========================
# [주의] SessionLocal 위치가 app/database.py가 맞는지 확인해주세요!
# 만약 에러나면 from app.core.database import SessionLocal 등으로 바꿔야 합니다.

from app.db.session import SessionLocal
from app.db.session import engine, SessionLocal  # engine 추가
from app.db.models import Base, Stock
from app.db.models import Stock

# =========================
# App instance
# =========================
app = FastAPI()

# =========================
# Middleware
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용 (테스트용)
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, PUT, DELETE 모두 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# =========================
# Helper Function: 주식 데이터 초기화
# =========================
def init_stock_data():
    """DB에 주식 데이터가 하나도 없으면 JSON 파일에서 읽어와 넣습니다."""
    db = SessionLocal()
    try:
        # 1. 데이터가 이미 있는지 확인
        count = db.query(Stock).count()
        if count > 0:
            print(f"✅ 이미 {count}개의 주식 데이터가 있습니다. 초기화 건너뜀.")
            return

        # 2. JSON 파일 경로 찾기 (main.py와 같은 폴더에 있다고 가정)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "DomesticStocks.json")

        if not os.path.exists(file_path):
            print(f"⚠️ 경고: {file_path} 파일을 찾을 수 없습니다.")
            return

        print("📂 초기 주식 데이터를 입력합니다...")
        
        # 3. JSON 읽기 및 DB 입력
        with open(file_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
            
        stocks_to_insert = []
        for item in data_list:
            stock = Stock(
                stock_id=item["Code"],
                stock_name=item["Name"]
            )
            stocks_to_insert.append(stock)
            
        db.add_all(stocks_to_insert)
        db.commit()
        print(f"🚀 성공! {len(stocks_to_insert)}개의 주식 데이터를 DB에 넣었습니다.")

    except Exception as e:
        print(f"❌ 주식 데이터 초기화 중 오류 발생: {e}")
        db.rollback()
    finally:
        db.close()

# =========================
# Startup event
# =========================
@app.on_event("startup")
def startup_event():
    # 1. 파이어베이스 초기화
    init_firebase()
    # 2. 주식 데이터 자동 주입 (추가된 부분)
    init_stock_data()

# =========================
# Router registration
# =========================
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(user_stock_router, prefix="/api")
app.include_router(agent_router, prefix="/api")

@app.on_event("startup")
def startup_event():
    # 1. 파이어베이스 초기화
    init_firebase()
    
    # 🛠️ [추가] DB 테이블 자동 생성
    # 이 명령어가 실행될 때 users, stocks, user_stocks 등 모든 테이블이 만들어집니다.
    try:
        print("🛠️ 데이터베이스 테이블 생성을 시작합니다...")
        Base.metadata.create_all(bind=engine)
        print("✅ 테이블 생성 완료!")
    except Exception as e:
        print(f"❌ 테이블 생성 중 오류 발생: {e}")

    # 2. 주식 데이터 자동 주입
    init_stock_data()