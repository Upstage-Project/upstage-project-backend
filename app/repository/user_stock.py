from sqlalchemy.orm import Session
from sqlalchemy import or_

# ✅ 너 프로젝트에 맞게 import 경로만 맞춰라
from app.db.models import Stock, UserStock


def get_stock_by_identifier(db: Session, identifier: str) -> Stock | None:
    """
    identifier가 종목코드('005930')이든 종목명('삼성전자')이든 둘 다 찾게.
    """
    identifier = identifier.strip()
    return (
        db.query(Stock)
        .filter(or_(Stock.stock_id == identifier, Stock.stock_name == identifier))
        .first()
    )


def search_stocks(db: Session, q: str, limit: int = 20) -> list[Stock]:
    q = q.strip()
    return (
        db.query(Stock)
        .filter(or_(Stock.stock_id.ilike(f"%{q}%"), Stock.stock_name.ilike(f"%{q}%")))
        .order_by(Stock.stock_id.asc())
        .limit(limit)
        .all()
    )


def get_user_stock_item(db: Session, user_id: int, stock_id: str) -> UserStock | None:
    """
    user_stocks 테이블이 (user_id, stock_id) 복합 PK 라는 가정.
    stock_id는 TEXT (ex: '005930')
    """
    return (
        db.query(UserStock)
        .filter(UserStock.user_id == user_id, UserStock.stock_id == stock_id)
        .first()
    )


def add_stock_to_user(db: Session, user_id: int, stock_id: str) -> UserStock:
    item = UserStock(user_id=user_id, stock_id=stock_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_user_stock_item(db: Session, user_id: int, stock_id: str) -> None:
    """
    복합키 기반으로 바로 삭제 (조회 후 delete)
    """
    item = get_user_stock_item(db, user_id, stock_id)
    if item:
        db.delete(item)
        db.commit()


def get_all_user_stocks(db: Session, user_id: int) -> list[Stock]:
    """
    user_stocks에 등록된 stock_id들을 stocks와 조인해서 Stock 리스트로 반환
    """
    return (
        db.query(Stock)
        .join(UserStock, UserStock.stock_id == Stock.stock_id)
        .filter(UserStock.user_id == user_id)
        .order_by(Stock.stock_id.asc())
        .all()
    )
