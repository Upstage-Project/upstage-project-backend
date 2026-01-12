# app/repository/client/search_client.py
import os
from langchain_community.utilities import GoogleSerperAPIWrapper
from app.repository.client.base import BaseSearchClient
from dotenv import load_dotenv

# 배포 환경(Kubernetes)에서는 ConfigMap/Secret으로 환경변수가 자동 주입되므로 .env 로드를 건너뜁니다.
if os.getenv("KUBERNETES_SERVICE_HOST") is None:
    load_dotenv()

class SerperSearchClient(BaseSearchClient):
    def __init__(self):
        # langchain의 유틸리티 래퍼를 사용하여 간편하게 구현
        self._search = GoogleSerperAPIWrapper()

    def search(self, query: str) -> str:
        return self._search.run(query)
