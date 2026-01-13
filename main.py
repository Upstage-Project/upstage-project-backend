from dotenv import load_dotenv
load_dotenv()

# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.users import router as users_router  # users 라우터 쓸 거면
from app.core.firebase import init_firebase

app = FastAPI()

# (선택) CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_firebase()

# ✅ app 만든 다음에 include_router 해야 함
app.include_router(auth_router)
app.include_router(users_router)
