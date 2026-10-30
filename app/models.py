"""ORM 모델. 요구사항정의서 5장 '데이터 모델'과 대응한다."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped[Profile | None] = relationship(back_populates="user", cascade="all, delete-orphan")
    consents: Mapped[list[Consent]] = relationship(cascade="all, delete-orphan")
    goals: Mapped[list[Goal]] = relationship(cascade="all, delete-orphan", order_by="Goal.id")
    plans: Mapped[list[BudgetPlan]] = relationship(cascade="all, delete-orphan", order_by="BudgetPlan.id")
    chat_sessions: Mapped[list[ChatSession]] = relationship(cascade="all, delete-orphan", order_by="ChatSession.id")
    memories: Mapped[list[Memory]] = relationship(cascade="all, delete-orphan", order_by="Memory.id")


class Consent(Base):
    """동의 이력. 필수(terms·privacy·overseas)와 선택(weekly_email) 항목을 구분해 저장한다."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    agreed: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(20), default="2026-09-30")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Profile(Base):
    """재무 프로필. 대화형 진단(FR-03)으로 채워지며 모든 AI 응답의 '사실의 원천'이다."""

    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    age: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(20))
    employment_type: Mapped[str | None] = mapped_column(String(20))
    company_size: Mapped[str | None] = mapped_column(String(20))
    monthly_income: Mapped[int | None] = mapped_column(Integer)
    annual_income: Mapped[int | None] = mapped_column(Integer)
    housing_type: Mapped[str | None] = mapped_column(String(20))
    rent: Mapped[int | None] = mapped_column(Integer)
    fixed_costs: Mapped[int | None] = mapped_column(Integer)
    debt_total: Mapped[int | None] = mapped_column(Integer)
    debt_monthly: Mapped[int | None] = mapped_column(Integer)
    savings: Mapped[int | None] = mapped_column(Integer)
    saving_monthly: Mapped[int | None] = mapped_column(Integer)  # 지금 매달 적금·저축에 넣는 돈 (유형 D 판정)
    goal_text: Mapped[str | None] = mapped_column(String(200))
    goal_amount: Mapped[int | None] = mapped_column(Integer)
    goal_months: Mapped[int | None] = mapped_column(Integer)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    target_amount: Mapped[int] = mapped_column(Integer)
    target_months: Mapped[int] = mapped_column(Integer)
    monthly_needed: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BudgetPlan(Base):
    """월급 배분 플랜(FR-05). 숫자는 계산 엔진이 만들고, 설명(explanation)만 AI가 쓴다."""

    __tablename__ = "budget_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    allocations: Mapped[list] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    explanation_by_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # onboarding | coach
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list[ChatMessage]] = relationship(
        cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    tools_used: Mapped[list] = mapped_column(JSON, default=list)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feedback: Mapped[list[Feedback]] = relationship(cascade="all, delete-orphan")


class Memory(Base):
    """장기 메모리(FR-10). 사용자가 '내 기억' 화면에서 직접 보고 지울 수 있다."""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # preference | commitment | fact
    content: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1 | -1
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
