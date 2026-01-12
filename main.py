from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.core.firebase import init_firebase
from app.api.auth import router as auth_router

app = FastAPI()

@app.on_event("startup")
def startup_event():
    init_firebase()

app.include_router(auth_router)
