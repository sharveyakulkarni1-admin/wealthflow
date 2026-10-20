from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    theme: Mapped[str] = mapped_column(String(16), default="system", server_default="system")
    date_format: Mapped[str] = mapped_column(String(8), default="iso", server_default="iso")
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recurring: Mapped[list["RecurringTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    savings_goals: Mapped[list["SavingsGoal"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    net_worth_items: Mapped[list["NetWorthItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    net_worth_snapshots: Mapped[list["NetWorthSnapshot"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
        Index("ix_transactions_user_category", "user_id", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # income / expense
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[str] = mapped_column(String(80), index=True)
    merchant: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    recurring_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")
    recurring: Mapped["RecurringTransaction | None"] = relationship(back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "month", "year", name="uq_budget_user_period_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)

    user: Mapped["User"] = relationship(back_populates="budgets")


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[str] = mapped_column(String(80))
    frequency: Mapped[str] = mapped_column(String(20))  # monthly, weekly, yearly
    next_due: Mapped[date] = mapped_column(Date, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="recurring")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="recurring")

    
class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        Index("ix_savings_goals_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    saved_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="savings_goals")


class NetWorthItem(Base):
    __tablename__ = "net_worth_items"
    __table_args__ = (
        Index("ix_net_worth_items_user_kind", "user_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="net_worth_items")


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_net_worth_snapshot_user_date"),
        Index("ix_net_worth_snapshots_user_date", "user_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    total_assets_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_liabilities_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_worth_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="net_worth_snapshots")


class TransactionImportBatch(Base):
    __tablename__ = "transaction_import_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_import_batch_user_request"),
        Index("ix_import_batches_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    content_digest: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="received", server_default="received")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="support_tickets")


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    members_can_manage_resources: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (UniqueConstraint("family_id", "user_id", name="uq_family_member_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member", server_default="member")
    share_financial_summary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilyInvitation(Base):
    __tablename__ = "family_invitations"
    __table_args__ = (
        UniqueConstraint("family_id", "email", name="uq_family_invitation_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyBudget(Base):
    __tablename__ = "family_budgets"
    __table_args__ = (
        UniqueConstraint("family_id", "category", "month", "year", name="uq_family_budget_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilyExpense(Base):
    __tablename__ = "family_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("family_budgets.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilySavingsGoal(Base):
    __tablename__ = "family_savings_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    saved_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilySavingsContribution(Base):
    __tablename__ = "family_savings_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("family_savings_goals.id", ondelete="CASCADE"), index=True
    )
    contributed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FamilyNotification(Base):
    __tablename__ = "family_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
