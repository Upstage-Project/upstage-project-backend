from sqlalchemy.orm import Session
from app.db.models import Question
from typing import List, Optional, Dict, Any
from sqlalchemy import select


def get_all_by_user(db: Session, user_id: int) -> List[Question]:
    """
    유저 ID로 모든 세션 목록을 조회합니다.
    """
    # filter_by를 사용하여 Pyright의 bool 오인 에러를 방지합니다.
    stmt = select(Question).filter_by(user_id=user_id)
    return list(db.scalars(stmt).all())


def get_sessions_first_interaction(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """
    유저의 모든 세션에서 첫 번째 대화 객체(질문/답변 쌍)를 추출합니다.
    """
    stmt = select(Question).filter_by(user_id=user_id)
    sessions = db.scalars(stmt).all()

    # 리스트 컴프리헨션을 사용하여 안전하게 추출
    # s.qa_list가 존재하고 요소가 있을 때만 0번 인덱스 추출
    return [
        s.qa_list[0]
        for s in sessions
        if s.qa_list and len(s.qa_list) > 0
    ]

def get_by_session_id(db: Session, user_id: int, session_id: str) -> Optional[Question]:
    """
    특정 세션 ID와 유저 ID가 일치하는 데이터를 조회합니다.
    """
    return db.query(Question).filter_by(
        user_id=user_id,
        session_id=session_id
    ).first()

def create_session(db: Session, user_id: int, session_id: str, qa_list: List[Dict[str, Any]] = None) -> Question:
    """
    새로운 대화 세션을 추가합니다.
    qa_list는 [{"question": "...", "answer": "..."}] 형태의 딕셔너리 리스트입니다.
    """
    if qa_list is None:
        qa_list = []

    new_session = Question(
        user_id=user_id,
        session_id=session_id,
        qa_list=qa_list
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


def update_qa_list(db: Session, question_obj: Question, new_qa_list: List[Dict[str, Any]]) -> Question:
    """
    기존 대화 리스트(딕셔너리 리스트)를 수정 또는 업데이트합니다.
    """
    question_obj.qa_list = new_qa_list
    db.commit()
    db.refresh(question_obj)
    return question_obj


def delete_session(db: Session, question_obj: Question):
    """
    세션 데이터를 삭제합니다.
    """
    db.delete(question_obj)
    db.commit()