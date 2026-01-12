from sqlalchemy import BigInteger, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    stock_name: Mapped[str] = mapped_column(Text, nullable=False)


class PfItem(Base):
    __tablename__ = "pf_items"
    __table_args__ = (
        UniqueConstraint("user_id", "stock_id", name="pf_user_stock_uniq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stocks.id"), nullable=False
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="questions_user_session_uniq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    qa_list: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
