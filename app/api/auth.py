from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel # 데이터 구조 정의용

from app.db.session import get_db
from app.db.models import User
import firebase_admin.auth as auth # 파이어베이스 검증용

router = APIRouter(prefix="/auth", tags=["auth"])

# 1. 프론트엔드가 보내는 JSON 모양 정의 ({ provider: ..., token: ... })
class LoginRequest(BaseModel):
    provider: str
    token: str

@router.post("/login")
def login(
    request: LoginRequest, # ★ Body로 데이터를 받겠다고 선언
    db: Session = Depends(get_db)
    # ❌ claims: dict = Depends(get_current_claims)  <-- 이 줄 삭제!!
):
    # 2. Body로 받은 토큰(request.token)을 직접 검증
    try:
        # 파이어베이스 Admin SDK로 토큰 유효성 검사 및 정보 추출
        decoded_token = auth.verify_id_token(request.token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
    except Exception as e:
        # 토큰이 가짜거나 만료됐으면 여기서 예외 처리
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    # 3. 이후 로직은 기존과 동일
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")
    if not email:
        raise HTTPException(status_code=400, detail="Token missing email")

    user = db.query(User).filter(User.firebase_uid == uid).first()

    if not user:
        user = User(firebase_uid=uid, email=email)
        db.add(user)
    else:
        if user.email != email:
            user.email = email

    db.commit()
    db.refresh(user)

    # 4. 프론트엔드에 돌려줄 데이터
    # (여기서 우리 서비스 전용 accessToken을 만들어 줄 수도 있음)
    return {
        "accessToken": request.token, # 일단은 받은 토큰을 그대로 주거나, JWT 생성해서 리턴
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
        }
    }