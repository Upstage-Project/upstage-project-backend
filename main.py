from dotenv import load_dotenv
load_dotenv()


# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# =========================
# Router imports
# =========================
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.routes.user_stock import router as user_stock_router
# from app.api.routes.agent_routers import router as agent_router  # 필요하면 나중에

from app.core.firebase import init_firebase

# =========================
# App instance
# =========================
app = FastAPI()

# =========================
# Middleware
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        # 프론트가 다른 PC면 추가
        # "http://10.111.134.X:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Startup event
# =========================
@app.on_event("startup")
def startup_event():
    init_firebase()

# =========================
# Router registration
# =========================
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(user_stock_router, prefix="/api")

# app.include_router(agent_router)  # 에이전트 API 쓸 때만 활성화
