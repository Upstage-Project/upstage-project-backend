import os
import glob
import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings

def _project_root() -> str:
    # 현재 작업 디렉토리(uvicorn 실행 위치)를 루트로 사용
    return os.path.abspath(os.getcwd())

def _find_service_account_json(root: str) -> str:
    candidates = glob.glob(os.path.join(root, "*adminsdk*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"Firebase service account json not found in: {root}\n"
            f"Expected something like '*adminsdk*.json'"
        )
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]

def init_firebase() -> None:
    if firebase_admin._apps:
        return

    # ✅ 1순위: .env의 firebase_credentials_file 사용
    key_path = getattr(settings, "firebase_credentials_file", None)

    # ✅ 2순위: 기존 방식(루트에서 *adminsdk*.json 자동 탐색)
    if not key_path:
        root = _project_root()
        key_path = _find_service_account_json(root)

    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Firebase credential file not found: {key_path}")

    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

def verify_firebase_token(id_token: str) -> dict:
    init_firebase()
    return auth.verify_id_token(id_token)
