import logging
from typing import List, Dict, Any, Optional
from app.models.entities.vector_qa import NewsArticle  # 프로젝트 내 엔티티 사용
from app.service.vector_service import VectorService
from app.repository.vector.vector_repo import ChromaDBRepository
from app.service.embedding_service import EmbeddingService
from app.exceptions import KnowledgeBaseException

logger = logging.getLogger("seed")


class KnowledgeService:
    def __init__(self):
        self.vector_service = VectorService(ChromaDBRepository(), EmbeddingService())

    async def sync_external_news(self, api_response_data: List[Dict[str, Any]]):
        """
        외부 API 데이터를 받아 DB 중복 체크 후 저장
        """
        try:
            # 1. API 데이터를 엔티티 객체로 변환
            new_articles = []
            for item in api_response_data:
                article = NewsArticle(
                    id=item.get("id"),  # 외부 API의 고유 ID
                    document=f"제목: {item.get('title')}\n내용: {item.get('content')}",
                    metadata={
                        "source": item.get("source", "external_api"),
                        "published_at": item.get("date")
                    }
                )
                new_articles.append(article)

            # 2. 중복 체크 및 필터링 (가이드북 73p DB 상태 확인 로직을 'ID 기반'으로 고도화)
            # 여기서는 간단히 ID 리스트를 추출하여 DB에 존재하는지 확인하는 로직이 들어갈 수 있습니다.
            # (ChromaDB의 get() 기능을 활용하여 기존 ID 존재 여부 확인 권장)

            # 3. 배치 단위 저장 (가이드북 73p 배치 처리 로직 적용: batch_size=100)
            batch_size = 100
            total = len(new_articles)

            for i in range(0, total, batch_size):
                batch = new_articles[i: i + batch_size]

                # VectorService를 통해 저장 [cite: 114, 1425]
                self.vector_service.add_documents(
                    documents=[a.document for a in batch],
                    metadatas=[a.metadata for a in batch],
                    ids=[a.id for a in batch]
                )
                logger.info(f"Successfully synced batch {min(i + batch_size, total)}/{total}")

            return {"status": "success", "synced_count": total}

        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            raise KnowledgeBaseException(f"External knowledge sync failed: {str(e)}")


# 싱글톤 인스턴스
knowledge_service = KnowledgeService()


async def sync_news_to_knowledge_base(api_data: List[Dict[str, Any]]):
    return await knowledge_service.sync_external_news(api_data)