# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.api.auth import router as auth_router
from app.api.users import router as users_router
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

app.include_router(auth_router)
app.include_router(users_router)
