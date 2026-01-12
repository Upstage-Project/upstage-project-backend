# app/deps.py
from fastapi.params import Depends

from app.repository.vector.vector_repo import (
    VectorRepository,
    ChromaDBRepository,
)
from app.service.vector_service import VectorService
from app.service.embedding_service import EmbeddingService


def get_vector_repository() -> VectorRepository:
    return ChromaDBRepository()


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def get_vector_service(
    vector_repo: VectorRepository = Depends(get_vector_repository),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> VectorService:
    return VectorService(
        vector_repository=vector_repo,
        embedding_service=embedding_service,
    )
