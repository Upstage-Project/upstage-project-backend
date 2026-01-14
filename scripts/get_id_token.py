import os
import requests
from dotenv import load_dotenv

# .env 강제 로딩
load_dotenv(".env")

from app.core.firebase import init_firebase
from app.core.config import settings
from firebase_admin import auth


def main():
    # settings 우선, 없으면 getenv fallback
    web_api_key = getattr(settings, "firebase_web_api_key", None) or os.getenv("FIREBASE_WEB_API_KEY")
    if not web_api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY is not set")

    # Firebase Admin 초기화
    init_firebase()

    uid = "test-user-001"
    custom_token = auth.create_custom_token(uid).decode("utf-8")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={web_api_key}"
    payload = {"token": custom_token, "returnSecureToken": True}

    r = requests.post(url, json=payload, timeout=20)

    # ✅ 400이면 여기서 BODY를 찍고 종료
    if not r.ok:
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
        raise SystemExit(1)

    data = r.json()
    print("ID_TOKEN=", data["idToken"])
    print("REFRESH_TOKEN=", data["refreshToken"])


if __name__ == "__main__":
    main()
