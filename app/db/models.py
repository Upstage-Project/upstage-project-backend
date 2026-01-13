from sqlalchemy import BigInteger, Text, ForeignKey, UniqueConstraint, Identity
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base



class User(Base):
    __tablename__ = "users"

    # BIGSERIAL/IDENTITY로 자동 증가 보장
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"

    # 티커(숫자든 문자든) PK: 반드시 TEXT (005930 같은 앞자리 0 보존)
    stock_id: Mapped[str] = mapped_column(Text, primary_key=True)
    stock_name: Mapped[str] = mapped_column(Text, nullable=False)


class UserStock(Base):
    __tablename__ = "user_stocks"
    # (user_id, stock_id) 복합 PK로 중복 방지
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    stock_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stocks.stock_id", ondelete="RESTRICT"), primary_key=True
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="questions_user_session_uniq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    qa_list: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
