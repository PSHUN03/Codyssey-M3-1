"""ORM 모델. 요구사항정의서 5장 '데이터 모델'과 대응한다."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    weekly_reports: Mapped[list[WeeklyReport]] = relationship(cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship(cascade="all, delete-orphan", order_by="Transaction.id")
    weekly_savings_checks: Mapped[list[WeeklySavingsCheck]] = relationship(cascade="all, delete-orphan")
    monthly_savings_records: Mapped[list[MonthlySavingsRecord]] = relationship(cascade="all, delete-orphan")


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
    saving_monthly: Mapped[int | None] = mapped_column(Integer)
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
    kind: Mapped[str] = mapped_column(String(20))
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
    role: Mapped[str] = mapped_column(String(20))
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
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 코치 맥락에 마지막으로 쓰인 시각


class LoginFailure(Base):
    """로그인 실패 횟수 (BE-03). 이메일 원문 대신 해시를 키로 쓴다."""

    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmUsage(Base):
    """Claude 호출 한 번의 사용량 (AI-05, NFR-08). 사용자 식별 정보와 대화 내용은 남기지 않는다."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # coach / structured / text / vision
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    stop_reason: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WeeklyReport(Base):
    """주간 리포트와 발송 기록. 같은 사용자·주에는 동일한 ID를 사용한다."""

    __tablename__ = "weekly_reports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    claim_token: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    """거래내역 (BE-01, FR-13·14). 원본 파일은 저장하지 않고, 가린 가맹점명과 금액만 남긴다. 지출은 음수다."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    merchant: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="upload")
class WeeklySavingsCheck(Base):
    """주간 저축 입금 체크."""

    __tablename__ = "weekly_savings_checks"
    __table_args__ = (
        UniqueConstraint("user_id", "week", name="uq_weekly_savings_user_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week: Mapped[str] = mapped_column(String(8))
    deposited: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MonthlySavingsRecord(Base):
    """월별 저축 금액 기록."""

    __tablename__ = "monthly_savings_records"
    __table_args__ = (
        UniqueConstraint("user_id", "month", name="uq_monthly_savings_user_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
