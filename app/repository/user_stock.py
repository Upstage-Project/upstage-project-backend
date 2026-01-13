from sqlalchemy.orm import Session
from sqlalchemy import or_, select
from app.db.models import Stock  # __tablename__ = "stock" 가정
from app.db.models import UserStock  # __tablename__ = "user_stock" 가정
from typing import Optional, List


def get_all_user_stocks(db: Session, user_id: int):
    """특정 유저가 등록한 모든 종목 정보(이름, 코드 등)를 가져옵니다."""
    return (
        db.query(Stock)
        .join(UserStock)
        .filter_by(user_id=user_id)  # 'UserStock.user_id == user_id' 대신 사용
        .all()
    )


def get_stock_by_identifier(db: Session, identifier: str) -> Optional[Stock]:
    """stock 테이블에서 종목 코드나 이름으로 정보를 조회합니다.
    포트폴리오에 주식 추가할 때 사용합니다."""
    return db.query(Stock).filter(
        or_(Stock.stock_id == identifier, Stock.stock_name == identifier)
    ).first()


def add_stock_to_user(db: Session, user_id: int, stock_id: str) -> UserStock:
    """user_stock 테이블에 새로운 행을 추가합니다."""
    db_user_stock = UserStock(user_id=user_id, stock_id=stock_id)
    db.add(db_user_stock)
    db.commit()
    db.refresh(db_user_stock)
    return db_user_stock


def get_user_stock_item(db: Session, user_id: int, stock_id: str) -> Optional[UserStock]:
    """filter_by를 사용하여 타입 경고를 방지하고 가독성을 높입니다."""
    return db.query(UserStock).filter_by(
        user_id=user_id,
        stock_id=stock_id
    ).first()


def delete_user_stock_item(db: Session, user_stock_item: UserStock):
    """user_stock 테이블에서 해당 행을 삭제합니다."""
    db.delete(user_stock_item)
    db.commit()


def get_all_stocks(db: Session) -> List[Stock]:
    """
    DB에 저장된 모든 종목 리스트를 가져옵니다.
    """
    return list(db.scalars(select(Stock)).all())


def search_stocks_by_keyword(db: Session, keyword: str) -> List[Stock]:
    """
    종목명 또는 코드에 키워드가 포함된 종목들을 검색합니다.
    """
    statement = select(Stock).where(
        or_(
            Stock.stock_name.ilike(f"%{keyword}%"),
            Stock.stock_id.ilike(f"%{keyword}%")
        )
    )
    return list(db.scalars(statement).all())
