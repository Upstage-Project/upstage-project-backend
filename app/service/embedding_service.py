import os
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

from app.core.llm import get_upstage_embeddings

class EmbeddingService:
    def __init__(self):
        self._embeddings = get_upstage_embeddings()

    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def create_embedding(self, text:str) -> List[float]:
        return self._embeddings.embed_query(text)