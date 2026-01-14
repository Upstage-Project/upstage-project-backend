import os
import sys
import time
import chromadb  # pip install chromadb
from typing import List, Dict, Any
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document

# 프로젝트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.orchestrator import run_investment_orchestrator
from langchain_upstage import UpstageEmbeddings
from langchain_chroma import Chroma
from app.agents.ticker_resolver import TickerResolver
from app.core.chroma_db import ChromaDBConfig

load_dotenv()


# -----------------------------------------------------------
# 1. [테스트용] 통합 VectorService (Memory Mode)
# -----------------------------------------------------------
class IntegratedVectorService:
    def __init__(self):
        print(f"   [Init] 테스트를 위해 '메모리 전용(Ephemeral)' DB를 사용합니다.")

        # [핵심 1] 파일 저장이 아닌, 메모리(RAM) 클라이언트 사용
        # 윈도우 + Python 3.13 충돌(0xC0000005)을 완벽하게 회피합니다.
        self.raw_client = chromadb.EphemeralClient()
        self.config = ChromaDBConfig()

        self.embedding = UpstageEmbeddings(model="solar-embedding-1-large")

        self.vector_store = Chroma(
            client=self.raw_client,
            collection_name=self.config.collection_name,
            embedding_function=self.embedding,
        )

    def search(self, query: str, n_results: int = 5) -> List[Document]:
        print(f"   [Search] '{query}' 검색 중...")
        try:
            docs = self.vector_store.similarity_search(query, k=n_results)
            print(f"   [Search] {len(docs)}개의 문서 발견.")
            return docs
        except Exception as e:
            print(f"⚠️ [Warning] 검색 중 오류: {e}")
            return []

    def add_documents(self, contents: List[str], metadatas: List[Dict[str, Any]]):
        if not contents: return

        print(f"   [Save] 문서 {len(contents)}건 처리 시작...")

        # [핵심 2] 메타데이터 안전 처리 (None -> 빈 문자열)
        safe_metadatas = []
        for meta in metadatas:
            new_meta = {}
            for k, v in meta.items():
                if v is None:
                    new_meta[k] = ""
                # 리스트나 딕셔너리가 오면 문자열로 변환
                elif not isinstance(v, (str, int, float, bool)):
                    new_meta[k] = str(v)
                else:
                    new_meta[k] = v
            safe_metadatas.append(new_meta)

        # [핵심 3] 길이 제한 강화 (3000 -> 1500자)
        # Upstage API 한도(4000토큰)를 절대 넘지 않게 안전하게 자름
        docs = []
        for content, meta in zip(contents, safe_metadatas):
            truncated_content = content[:1500]
            docs.append(Document(page_content=truncated_content, metadata=meta))

        try:
            # 메모리 DB이므로 배치 없이 한 번에 넣어도 빠르고 안전함
            self.vector_store.add_documents(docs)
            print(f"   [Save] {len(docs)}건 메모리 저장 완료.")
        except Exception as e:
            print(f"❌ [Error] 저장 실패: {e}")


# -----------------------------------------------------------
# 3. 실제 실행 함수
# -----------------------------------------------------------
def run_real_test(user_query: str):
    print("🚀 [Memory Execution] 크래시 방지 모드 테스트 시작...\n")

    if not os.getenv("UPSTAGE_API_KEY"):
        print("❌ 오류: UPSTAGE_API_KEY가 없습니다.")
        return

    try:
        vector_service = IntegratedVectorService()

        config = {
            "recursion_limit": 300,
            "configurable": {
                "vector_service": vector_service,
                "ticker_resolver": TickerResolver(),
                "dart_api_key": os.getenv("DART_API_KEY"),
                "db_engine": None,
            }
        }

        result = run_investment_orchestrator(
            user_query=user_query,
            user_id="memory_test_user",
            config=config
        )

        print("\n" + "=" * 50)
        print("✅ [Final Answer] 최종 답변 결과")
        print("=" * 50)
        print(result.get("final_answer"))

        # 검증 (메모리에 잘 들어갔나 확인)
        print("\n" + "=" * 50)
        print("🔍 [Verify] 메모리 DB 확인")
        print("=" * 50)
        docs = vector_service.search("매출", n_results=1)
        if docs:
            print(f"💾 검색 성공: {docs[0].page_content[:50]}...")
        else:
            print("💾 검색 결과 없음.")

    except Exception as e:
        print(f"\n❌ 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    query = "삼성전자의 최근 뉴스와 실적을 알려줘"
    run_real_test(query)