# app/db/models.py
from sqlalchemy import BigInteger, Text, ForeignKey, UniqueConstraint, Identity
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"
    stock_id: Mapped[str] = mapped_column(Text, primary_key=True)  # 티커 PK
    stock_name: Mapped[str] = mapped_column(Text, nullable=False)


class UserStock(Base):
    __tablename__ = "user_stocks"
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

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    qa_list: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
