# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# 기존 라우터
from app.api.auth import router as auth_router
from app.api.users import router as users_router

# [추가됨] Agent 및 Stock 라우터 임포트
from app.api.routes.agent_routers import router as agent_router
from app.api.routes.user_stock import router as user_stock_router

from app.core.firebase import init_firebase

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        # 프론트가 다른 PC면 그 주소 추가
        # 예: "http://10.111.134.X:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_firebase()

# 라우터 등록
app.include_router(auth_router)
app.include_router(users_router)
#app.include_router(agent_router)      # [추가됨] 에이전트 관련 API (/agent)
app.include_router(user_stock_router) # [추가됨] 주식 포트폴리오 API (/user-stock)