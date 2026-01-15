# app/models/schemas/agent.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class BaseSchema(BaseModel):
    """기본 스키마 클래스"""

    class Config:
        from_attributes = True


# ----
# 채팅 관련 스키마 정의
# ----

class ChatRequest(BaseSchema):
    """채팅 요청"""
    query: str = Field(..., description="유저 질의")
    session_id: Optional[str] = Field(None, description="세션 ID (없으면 서버에서 생성 가능)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="추가 메타데이터")


class ChatResponse(BaseSchema):
    """채팅 응답"""
    answer: str = Field(..., description="최종 답변")
    session_id: Optional[str] = Field(None, description="세션 ID")


class StreamEvent(BaseSchema):
    """SSE 스트림 이벤트 공통"""
    type: Literal["token", "log", "error"] = Field(..., description="이벤트 타입")


class TokenStreamEvent(StreamEvent):
    type: Literal["token"] = "token"
    answer: str = Field(..., description="스트리밍 토큰(부분 문자열)")


class LogStreamEvent(StreamEvent):
    type: Literal["log"] = "log"
    log: str = Field(..., description="로그 메시지")


class ErrorStreamEvent(StreamEvent):
    type: Literal["error"] = "error"
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
