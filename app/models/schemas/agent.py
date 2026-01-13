from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# 서비스에서 사용할 요청/응답 규격

class BaseSchema(BaseModel):
    """기본 스키마 클래스"""

    class Config:
        from_attributes = True


# ----
# 채팅 관련 스키마 정의
# ----

class ChatRequest(BaseSchema):
    """채팅 요청 스키마"""
    query: str = Field(..., description="사용자 질문")
    session_id: Optional[str] = Field(None, description="세션 ID")


class ChatResponse(BaseSchema):
    """채팅 응답 스키마"""
    answer: str = Field(..., description="에이전트 답변")
    user_query: Optional[str] = Field(None, description="사용자 질문")
    process_status: Optional[str] = Field(None, description="처리 상태")
    loop_count: Optional[int] = Field(None, description="루프 횟수")


# ----
# 스트림 관련 스키마 정의 (스트리밍은 답변이 생성되는 대로 즉시 클라이언트에 전달합니다.
# 사용자는 글자가 하나씩 타이핑되는 것을 보며 서비스가 작동 중임을 인지하고, 훨씬 빠르다고 느끼게 됩니다.)
# ----

class StreamEvent(BaseSchema):
    """스트림 이벤트 기본 스키마"""
    type: str = Field(..., description="이벤트 타입 (token, log, error)")


class TokenStreamEvent(StreamEvent):
    """토큰 스트림 이벤트 스키마"""
    type: str = Field("token", description="이벤트 타입")
    answer: str = Field(..., description="생성된 답변 토큰")


class LogStreamEvent(StreamEvent):
    """로그 스트림 이벤트 스키마"""
    type: str = Field("log", description="이벤트 타입")
    log: str = Field(..., description="로그 메시지")


class ErrorStreamEvent(StreamEvent):
    """에러 스트림 이벤트 스키마"""
    type: str = Field("error", description="이벤트 타입")
    error: str = Field(..., description="에러 메시지")


# ----
# 지식 정보 관련 스키마 정의
# ----

class AddKnowledgeRequest(BaseSchema):
    """지식 추가 요청 스키마"""
    documents: List[str] = Field(..., description="추가할 문서 리스트")
    metadatas: Optional[List[Dict[str, Any]]] = Field(None, description="문서별 메타데이터 리스트")


class KnowledgeResponse(BaseSchema):
    """지식 작업 응답 스키마"""
    status: str = Field(..., description="상태 (success/error)")
    message: str = Field(..., description="결과 메시지")