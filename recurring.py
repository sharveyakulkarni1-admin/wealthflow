from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import RecurringTransaction, Transaction


def advance_due(due: date, frequency: str) -> date:
    if frequency == "weekly":
        return due + relativedelta(weeks=1)
    if frequency == "monthly":
        return due + relativedelta(months=1)
    return due + relativedelta(years=1)


async def process_recurring(db: AsyncSession, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    result = await db.execute(
        select(RecurringTransaction).where(
            RecurringTransaction.active.is_(True),
            RecurringTransaction.next_due <= as_of,
        )
    )
    items = result.scalars().all()
    created = 0

    for item in items:
        while item.next_due <= as_of:
            tx = Transaction(
                user_id=item.user_id,
                transaction_date=item.next_due,
                kind=item.kind,
                amount=item.amount,
                currency=item.currency,
                category=item.category,
                merchant=item.name,
                note=f"Generated from recurring transaction #{item.id}",
                tags="recurring",
                recurring_id=item.id,
            )
            db.add(tx)
            created += 1
            item.next_due = advance_due(item.next_due, item.frequency)

    if created:
        await db.commit()
    return created
