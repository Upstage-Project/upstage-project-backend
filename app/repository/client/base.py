# app/repository/client/base.py
from abc import ABC, abstractmethod

class BaseClient(ABC):
    @abstractmethod
    def get_chat_model(self):
        pass
    @abstractmethod
    def get_embedding_model(self):
        pass

class BaseSearchClient(ABC):
    @abstractmethod
    def search(self, query: str) -> str:
        """
        검색 쿼리를 받아 문자열 형태의 결과를 반환해야 함
        """
        pass
