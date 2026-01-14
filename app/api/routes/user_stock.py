from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repository import user_stock as user_stock_repo

# =========================
# Request Models
# =========================
class StockRequest(BaseModel):
    identifier: str  # 종목코드 or 종목명

router = APIRouter(prefix="/user-stock", tags=["UserStock"])


# =========================
# 포트폴리오 종목 추가
# =========================
@router.post("/items", status_code=status.HTTP_201_CREATED)
def add_to_portfolio(
    request: StockRequest,
    db: Session = Depends(get_db),
    user_id: int = 1  # TODO: 추후 인증된 유저 ID로 교체
):
    stock = user_stock_repo.get_stock_by_identifier(db, request.identifier)
    if not stock:
        raise HTTPException(status_code=404, detail="존재하지 않는 종목입니다.")

    # ✅ stock.id 가 아니라 stock.stock_id (TEXT PK)
    existing_item = user_stock_repo.get_user_stock_item(db, user_id, stock.stock_id)
    if existing_item:
        raise HTTPException(status_code=400, detail="이미 등록된 종목입니다.")

    user_stock_repo.add_stock_to_user(db, user_id, stock.stock_id)
    return {"message": f"{stock.stock_name} 추가 완료"}


# =========================
# 포트폴리오 종목 목록
# =========================
@router.get("/items")
def list_user_stocks(
    db: Session = Depends(get_db),
    user_id: int = 1  # TODO: 추후 인증된 유저 ID로 교체
):
    stocks = user_stock_repo.get_all_user_stocks(db, user_id)
    return [
        {
            "stock_id": s.stock_id,
            "stock_name": s.stock_name,
        }
        for s in stocks
    ]


# =========================
# 포트폴리오 종목 삭제
# =========================
@router.delete("/items", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_portfolio(
    identifier: str,
    db: Session = Depends(get_db),
    user_id: int = 1  # TODO: 추후 인증된 유저 ID로 교체
):
    stock = user_stock_repo.get_stock_by_identifier(db, identifier)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    # ✅ stock.id 가 아니라 stock.stock_id
    user_stock_item = user_stock_repo.get_user_stock_item(db, user_id, stock.stock_id)
    if not user_stock_item:
        raise HTTPException(status_code=404, detail="등록되지 않은 종목입니다.")

    user_stock_repo.delete_user_stock_item(db, user_id, stock.stock_id)
    return None


# =========================
# 종목 검색
# =========================
@router.get("/stocks/search")
def search_stocks(
    q: str = Query(..., min_length=1, description="종목명 또는 종목코드"),
    db: Session = Depends(get_db),
):
    items = user_stock_repo.search_stocks(db, q, limit=20)
    return [{"stock_id": s.stock_id, "stock_name": s.stock_name} for s in items]