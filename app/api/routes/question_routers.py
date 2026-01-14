from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.repository import question as question_repo
from app.db.models import User
from app.db.session import get_db
from app.api.user_deps import get_current_user
from datetime import datetime, timezone

router = APIRouter(prefix="/questions", tags=["questions"])


# --- 스키마 정의 ---

class QAPair(BaseModel):
    question: str = Field(..., description="사용자 질문")
    answer: Optional[str] = Field(None, description="에이전트 답변")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AppendQARequest(BaseModel):
    qa_pair: QAPair


# --- API 엔드포인트 ---

@router.get("/sessions/first-questions", response_model=List[Dict[str, Any]])
async def list_sessions_first_question(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    모든 세션의 첫 번째 대화(질문/답변) 목록을 조회합니다.
    사이드바 등에서 대화의 시작 주제를 보여주는 용도입니다.
    """
    try:
        # 리포지토리의 get_sessions_first_interaction를 호출하여
        # {"session_id": ..., "first_interaction": ...} 리스트를 반환합니다.
        results = question_repo.get_sessions_first_interaction(db, current_user.id)
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching first questions: {str(e)}"
        )



@router.get("/sessions/{session_id}")
async def get_session_detail(
        session_id: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    특정 세션의 전체 대화 상세 내역을 조회합니다.
    """
    session = question_repo.get_by_session_id(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")

    return {
        "session_id": session.session_id,
        "qa_list": session.qa_list
    }


@router.post("/sessions/{session_id}/append")
async def append_qa_to_history(
        session_id: str,
        request: AppendQARequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    기존 대화 세션에 새로운 질문/답변 쌍을 추가합니다.
    """
    session = question_repo.get_by_session_id(db, current_user.id, session_id)

    # 1. Pydantic 모델을 딕셔너리로 변환
    new_qa_item = request.qa_pair.model_dump()

    # 2. 서버 기준으로 생성 시각 추가 (ISO-8601 형식)
    # UTC 기준 시간을 권장하며, 필요시 KST(+09:00)로 변환할 수 있습니다.
    new_qa_item["created_at"] = datetime.now(timezone.utc).isoformat()

    if not session:
        # 신규 세션 생성
        question_repo.create_session(db, current_user.id, session_id, [new_qa_item])
    else:
        # 기존 세션 업데이트 (JSONB 필드는 가변 객체이므로 복사본을 만들어 업데이트하는 것이 안전합니다)
        current_list = list(session.qa_list) if session.qa_list else []
        current_list.append(new_qa_item)
        question_repo.update_qa_list(db, session, current_list)

    return {"message": "대화가 성공적으로 기록되었습니다.", "timestamp": new_qa_item["created_at"]}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_history(
        session_id: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    특정 대화 세션을 삭제합니다.
    """
    session = question_repo.get_by_session_id(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="삭제할 기록이 없습니다.")

    question_repo.delete_session(db, session)
    return None