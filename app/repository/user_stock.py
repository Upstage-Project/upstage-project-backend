from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.stock import Stock  # __tablename__ = "stock" 가정
from app.models.user_stock import UserStock  # __tablename__ = "user_stock" 가정
from typing import Optional


def get_all_user_stocks(db: Session, user_id: int):
    """특정 유저가 등록한 모든 종목 정보(이름, 코드 등)를 가져옵니다."""
    return db.query(Stock).join(UserStock).filter(UserStock.user_id == user_id).all()

def get_stock_by_identifier(db: Session, identifier: str) -> Optional[Stock]:
    """stock 테이블에서 종목 코드나 이름으로 정보를 조회합니다."""
    return db.query(Stock).filter(
        or_(Stock.stock_id == identifier, Stock.stock_name == identifier)
    ).first()

def add_stock_to_user(db: Session, user_id: int, stock_id: int) -> UserStock:
    """user_stock 테이블에 새로운 행을 추가합니다."""
    db_user_stock = UserStock(user_id=user_id, stock_id=stock_id)
    db.add(db_user_stock)
    db.commit()
    db.refresh(db_user_stock)
    return db_user_stock

def get_user_stock_item(db: Session, user_id: int, stock_id: int) -> Optional[UserStock]:
    """특정 유저가 특정 종목을 이미 보유(등록)하고 있는지 user_stock에서 확인합니다."""
    return db.query(UserStock).filter(
        UserStock.user_id == user_id,
        UserStock.stock_id == stock_id
    ).first()

def delete_user_stock_item(db: Session, user_stock_item: UserStock):
    """user_stock 테이블에서 해당 행을 삭제합니다."""
    db.delete(user_stock_item)
    db.commit()
