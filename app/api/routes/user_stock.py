# app/api/routes/user_stock.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.repository import user_stock as user_stock_repo

from app.db.models import User
from app.api.user_deps import get_current_user

class StockRequest(BaseModel):
    identifier: str

class StockResponse(BaseModel):
    stock_id: str
    stock_name: str

    class Config:
        from_attributes = True

router = APIRouter(prefix="/user-stock", tags=["UserStock"])


@router.post("/items", status_code=status.HTTP_201_CREATED)
def add_to_portfolio(
        request: StockRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user) # 토큰 검증 후 유저 객체 반환
):
    """
    사용자의 포트폴리오에 새로운 종목을 추가합니다.
    1. 종목 존재 여부 확인
    2. 중복 등록 여부 확인 후 추가를 진행합니다.
    """
    # 1. stock 테이블에 존재하는 종목인지 확인
    stock = user_stock_repo.get_stock_by_identifier(db, request.identifier)
    if not stock:
        raise HTTPException(status_code=404, detail="존재하지 않는 종목입니다.")

    # 2. user_stock 테이블에 이미 등록된 관계인지 확인 (current_user.id 사용)
    existing_item = user_stock_repo.get_user_stock_item(db, current_user.id, stock.id)
    if existing_item:
        raise HTTPException(status_code=400, detail="이미 등록된 종목입니다.")

    # 3. 추가 실행 (current_user.id 사용)
    user_stock_repo.add_stock_to_user(db, current_user.id, stock.id)
    return {"message": f"{stock.stock_name} 추가 완료"}


@router.get("/items")
def list_user_stocks(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user) # 토큰 검증 후 유저 객체 반환
):
    """
    현재 로그인한 유저의 포트폴리오에 등록된 전체 종목 리스트를 반환합니다.
    """
    # current_user.id 사용
    stocks = user_stock_repo.get_all_user_stocks(db, current_user.id)

    # 결과를 보기 좋게 리스트 형태로 반환
    return [
        {"stock_id": s.stock_id, "stock_name": s.stock_name}
        for s in stocks
    ]


@router.delete("/items", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_portfolio(
        identifier: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user) # 토큰 검증 후 유저 객체 반환
):
    """
    사용자의 포트폴리오에서 특정 종목을 삭제합니다.
    """
    # 1. stock 테이블에서 종목 조회
    stock = user_stock_repo.get_stock_by_identifier(db, identifier)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    # 2. user_stock 테이블에서 해당 유저와의 관계 조회 (current_user.id 사용)
    user_stock_item = user_stock_repo.get_user_stock_item(db, current_user.id, stock.id)
    if not user_stock_item:
        raise HTTPException(status_code=404, detail="등록되지 않은 종목입니다.")

    # 3. 삭제 실행
    user_stock_repo.delete_user_stock_item(db, user_stock_item)
    return None


@router.get("/stocks", response_model=List[StockResponse])
def get_all_stocks(db: Session = Depends(get_db)):
    """
    시스템 DB에 등록된 모든 종목의 마스터 리스트를 반환합니다.
    """
    return user_stock_repo.get_all_stocks(db)


@router.get("/stocks/search", response_model=List[StockResponse])
def search_stocks(
    q: str = Query(..., description="검색할 종목명 또는 코드"),
    db: Session = Depends(get_db)
):
    """
    검색어(종목명 또는 코드)를 포함하는 종목을 찾아 리스트로 반환합니다.
    예: /user-stock/stocks/search?q=삼성
    """
    stocks = user_stock_repo.search_stocks_by_keyword(db, q)
    return stocks