from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from currency import convert
from models import Budget, RecurringTransaction, SavingsGoal, Transaction, User


ZERO = Decimal("0.00")


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month_start(value: date) -> date:
    start = _month_start(value)
    return (start - timedelta(days=1)).replace(day=1)


def _month_end(start: date) -> date:
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _periods(question: str, today: date) -> tuple[dict[str, date], dict[str, date] | None]:
    query = question.casefold()
    if "last week" in query or "previous week" in query:
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        previous_end = start - timedelta(days=1)
        return (
            {"label": "last week", "start": start, "end": end},
            {"label": "the week before", "start": previous_end - timedelta(days=6), "end": previous_end},
        )
    if "this week" in query or "past week" in query or "last 7 days" in query:
        start = today - timedelta(days=6)
        previous_end = start - timedelta(days=1)
        return (
            {"label": "the last 7 days", "start": start, "end": today},
            {"label": "the 7 days before that", "start": previous_end - timedelta(days=6), "end": previous_end},
        )
    if "last month" in query or "previous month" in query:
        end = _month_start(today) - timedelta(days=1)
        start = _month_start(end)
        previous_end = start - timedelta(days=1)
        return (
            {"label": "last month", "start": start, "end": end},
            {"label": "the month before", "start": _month_start(previous_end), "end": previous_end},
        )

    start = _month_start(today)
    previous_start = _previous_month_start(today)
    comparison_days = min(today.day, _month_end(previous_start).day)
    return (
        {"label": "this month to date", "start": start, "end": today},
        {
            "label": "the same dates last month",
            "start": previous_start,
            "end": previous_start + timedelta(days=comparison_days - 1),
        },
    )


def _wants(question: str, terms: tuple[str, ...]) -> bool:
    query = question.casefold()
    return any(term in query for term in terms)


async def _transaction_summary(
    db: AsyncSession,
    user: User,
    period: dict[str, date],
) -> dict[str, Any]:
    rows = await db.execute(
        select(
            Transaction.kind,
            Transaction.currency,
            Transaction.category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .where(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= period["start"],
            Transaction.transaction_date <= period["end"],
        )
        .group_by(Transaction.kind, Transaction.currency, Transaction.category)
    )

    income = ZERO
    expenses = ZERO
    by_category: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    count = 0
    for kind, currency, category, amount, row_count in rows.all():
        try:
            base_amount = convert(Decimal(amount or 0), currency, user.base_currency)
        except (KeyError, ArithmeticError):
            continue
        count += int(row_count)
        if kind == "income":
            income += base_amount
        else:
            expenses += base_amount
            by_category[category] += base_amount

    ordered_categories = sorted(by_category.items(), key=lambda item: item[1], reverse=True)
    return {
        "period": period["label"],
        "start_date": period["start"].isoformat(),
        "end_date": period["end"].isoformat(),
        "reporting_currency": user.base_currency,
        "transaction_count": count,
        "income": _quantize(income),
        "expenses": _quantize(expenses),
        "net_cash_flow": _quantize(income - expenses),
        "expense_by_category": [
            {"category": name, "amount": _quantize(amount), "currency": user.base_currency}
            for name, amount in ordered_categories[:8]
        ],
    }


async def build_financial_context(
    db: AsyncSession,
    user: User,
    question: str,
) -> dict[str, Any]:
    """Return small, deterministic summaries scoped to this user and question."""
    query = question.casefold()
    today = date.today()
    current_period, comparison_period = _periods(query, today)
    wants_budget = _wants(query, ("budget", "budgets", "spending limit", "within my limit"))
    wants_goals = _wants(query, ("goal", "goals", "save", "saving", "savings"))
    wants_recurring = _wants(query, ("recurring", "subscription", "subscriptions", "repeat"))
    wants_duplicates = _wants(query, ("duplicate", "duplicates", "same transaction"))
    wants_comparison = _wants(query, ("compare", "comparison", "increased", "increase", "decreased", "trend", "trends", "previous", "last month", "last week"))
    wants_transactions = _wants(query, ("transaction", "transactions", "spent", "spending", "expense", "expenses", "income", "category", "categories", "cash flow", "cashflow", "money", "month", "week"))

    context: dict[str, Any] = {
        "as_of": today.isoformat(),
        "reporting_currency": user.base_currency,
        "data_sections": [],
        "data_notes": [],
    }

    if wants_transactions or wants_budget or wants_duplicates:
        current = await _transaction_summary(db, user, current_period)
        context["transactions"] = {"current_period": current}
        context["data_sections"].append("transaction totals and category summaries")
        if wants_comparison:
            comparison = await _transaction_summary(db, user, comparison_period)
            context["transactions"]["comparison_period"] = comparison

    if wants_budget:
        budgets_result = await db.execute(
            select(Budget)
            .where(Budget.user_id == user.id, Budget.month == today.month, Budget.year == today.year)
            .order_by(Budget.category)
            .limit(50)
        )
        budgets = budgets_result.scalars().all()
        category_rows = await db.execute(
            select(Transaction.category, Transaction.currency, func.sum(Transaction.amount))
            .where(
                Transaction.user_id == user.id,
                Transaction.kind == "expense",
                Transaction.transaction_date >= _month_start(today),
                Transaction.transaction_date <= today,
            )
            .group_by(Transaction.category, Transaction.currency)
        )
        current_spending: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        for category, currency, amount in category_rows.all():
            try:
                current_spending[category.casefold()] += convert(Decimal(amount or 0), currency, user.base_currency)
            except (KeyError, ArithmeticError):
                continue
        context["budgets"] = [
            {
                "category": budget.category,
                "period": f"{budget.year:04d}-{budget.month:02d}",
                "limit": _quantize(budget.amount),
                "currency": user.base_currency,
                "spent": _quantize(current_spending[budget.category.casefold()]),
                "remaining": _quantize(budget.amount - current_spending.get(budget.category.casefold(), ZERO)),
            }
            for budget in budgets
        ]
        context["data_sections"].append("current-month budgets")

    if wants_goals:
        goals_result = await db.execute(
            select(SavingsGoal)
            .where(SavingsGoal.user_id == user.id)
            .order_by(SavingsGoal.created_at.desc())
            .limit(50)
        )
        goals = goals_result.scalars().all()
        context["saving_goals"] = [
            {
                "name": goal.name,
                "target": _quantize(goal.target_amount),
                "saved": _quantize(goal.saved_amount),
                "remaining": _quantize(max(ZERO, goal.target_amount - goal.saved_amount)),
                "currency": goal.currency,
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
                "status": (
                    "completed" if goal.saved_amount >= goal.target_amount
                    else "overdue" if goal.deadline and goal.deadline < today
                    else "active"
                ),
            }
            for goal in goals
        ]
        context["data_sections"].append("saving goals (each in its own currency)")
        if _wants(query, ("this month", "month", "monthly", "saved this week", "contributed")):
            context["data_notes"].append(
                "Goal records contain current balance snapshots, not dated deposits/withdrawals; monthly contributions and total cash savings cannot be calculated. Do not infer them from a goal balance."
            )

    if wants_recurring:
        recurring_result = await db.execute(
            select(RecurringTransaction)
            .where(RecurringTransaction.user_id == user.id, RecurringTransaction.active.is_(True))
            .order_by(RecurringTransaction.next_due)
            .limit(50)
        )
        recurring = recurring_result.scalars().all()
        context["recurring_transactions"] = [
            {
                "name": item.name,
                "amount": _quantize(item.amount),
                "currency": item.currency,
                "frequency": item.frequency,
                "category": item.category,
                "next_due": item.next_due.isoformat(),
            }
            for item in recurring
        ]
        context["data_sections"].append("active recurring transactions")

    if wants_duplicates:
        duplicate_rows = await db.execute(
            select(
                Transaction.transaction_date,
                Transaction.kind,
                Transaction.amount,
                Transaction.currency,
                Transaction.category,
                Transaction.merchant,
            )
            .where(
                Transaction.user_id == user.id,
                Transaction.transaction_date >= today - timedelta(days=60),
                Transaction.transaction_date <= today,
            )
            .order_by(Transaction.transaction_date.desc())
            .limit(500)
        )
        signatures = Counter(
            (
                row.transaction_date,
                row.kind,
                row.amount,
                row.currency,
                row.category.casefold(),
                (row.merchant or "").casefold(),
            )
            for row in duplicate_rows
        )
        context["possible_duplicate_groups"] = sum(1 for count in signatures.values() if count > 1)
        context["duplicate_check_period"] = "the last 60 days"
        context["data_sections"].append("possible duplicate transaction candidates")

    if wants_transactions and "transactions" in context:
        recent_result = await db.execute(
            select(
                Transaction.transaction_date,
                Transaction.kind,
                Transaction.amount,
                Transaction.currency,
                Transaction.category,
                Transaction.merchant,
            )
            .where(
                Transaction.user_id == user.id,
                Transaction.transaction_date >= current_period["start"],
                Transaction.transaction_date <= current_period["end"],
            )
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .limit(10)
        )
        context["recent_transactions"] = [
            {
                "date": row.transaction_date.isoformat(),
                "type": row.kind,
                "amount": _quantize(row.amount),
                "currency": row.currency,
                "category": row.category,
                "merchant": row.merchant,
            }
            for row in recent_result
        ]

    return context
