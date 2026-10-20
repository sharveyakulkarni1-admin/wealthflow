import csv
import io
from datetime import date
from decimal import Decimal
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import Transaction, User
from currency import convert


async def get_export_rows(db: AsyncSession, user: User):
    result = await db.execute(
        select(Transaction).where(Transaction.user_id == user.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    rows = []
    for t in result.scalars().all():
        rows.append({
            "date": t.transaction_date.isoformat(),
            "kind": t.kind,
            "amount": float(t.amount),
            "currency": t.currency,
            "amount_base": float(convert(t.amount, t.currency, user.base_currency)),
            "category": t.category,
            "merchant": t.merchant,
            "note": t.note,
            "tags": t.tags,
        })
    return rows


def csv_bytes(rows):
    output = io.StringIO()
    fields = ["date", "kind", "amount", "currency", "amount_base", "category", "merchant", "note", "tags"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def xlsx_bytes(rows):
    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    fields = ["date", "kind", "amount", "currency", "amount_base", "category", "merchant", "note", "tags"]
    ws.append(fields)
    for row in rows:
        ws.append([row[f] for f in fields])
    ws.freeze_panes = "A2"
    widths = [14, 12, 14, 12, 16, 20, 24, 42, 30]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    wb.save(output)
    return output.getvalue()
