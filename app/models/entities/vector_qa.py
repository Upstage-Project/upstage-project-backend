from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class BaseEntity(BaseModel):
    """기본 엔티티 클래스 (내부 데이터 타입 명세)"""
    class Config:
        from_attributes = True


class NewsArticle(BaseEntity):
    """
    뉴스 기사 엔티티
    """
    id: Optional[str] = Field(None, description="기사 식별자")
    document: str = Field(..., description="기사 내용")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터 (제목, 기자, 날짜 등)")


class FinancialStatement(BaseEntity):
    """
    재무제표 엔티티
    """
    id: Optional[str] = Field(None, description="보고서 식별자")
    document: str = Field(..., description="재무 수치 및 설명")
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "ticker": "",      # 종목 코드
            "fiscal_year": 0,  # 회계 연도
            "quarter": "",     # 분기 (1Q, 2Q 등)
            "report_type": ""  # 보고서 종류
        }
    )