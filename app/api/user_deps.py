from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User

# Bearer Token 추출기
security = HTTPBearer()


def get_current_claims(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    HTTP Header의 Bearer Token을 파싱하여 Firebase Admin SDK로 검증합니다.
    검증 성공 시 토큰의 payload(claims)를 반환합니다.
    """
    token = credentials.credentials
    try:
        # Firebase 토큰 검증
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        # 토큰 만료, 위변조 등 모든 인증 실패
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
        claims: dict = Depends(get_current_claims),
        db: Session = Depends(get_db)
) -> User:
    """
    검증된 토큰(claims)의 UID를 사용하여
    DB에서 실제 User 객체를 조회하여 반환합니다.
    """
    uid = claims.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")

    # DB에서 유저 조회
    user = db.query(User).filter(User.firebase_uid == uid).first()

    if not user:
        # (선택사항) 회원가입이 안 된 상태라면 404를 띄우거나, 여기서 자동 가입시킬 수도 있습니다.
        # 여기서는 보안을 위해 401 또는 404로 처리합니다.
        raise HTTPException(status_code=404, detail="User not found in database")

    return user