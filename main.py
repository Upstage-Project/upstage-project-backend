from dotenv import load_dotenv
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
        "http://10.111.134.6:5173",
        "http://10.111.134.16:5173",
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
app.include_router(agent_router, prefix="/api")
