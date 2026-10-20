from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
from html import escape
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from jose import JWTError, jwt
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_provider import AIProviderError
from ai_service import AIServiceError, chat as chat_with_ai
from analytics import dashboard_analytics
from auth import create_access_token, get_current_user, hash_password, verify_password
from currency import convert
from database import SessionLocal, get_db, init_db, settings
from exports import csv_bytes, get_export_rows, xlsx_bytes
from family import router as family_router
from models import (
    Budget,
    NetWorthItem,
    NetWorthSnapshot,
    RecurringTransaction,
    SavingsGoal,
    SupportTicket,
    Transaction,
    TransactionImportBatch,
    User,
)
from recurring import process_recurring
from schemas import (
    BudgetCreate,
    BudgetOut,
    LoginRequest,
    NetWorthItemInput,
    NetWorthItemOut,
    NetWorthSnapshotOut,
    NetWorthSummaryOut,
    RecurringCreate,
    RecurringOut,
    TransactionCreate,
    TransactionOut,
    UserCreate,
    UserOut,
    SavingsGoalCreate,
    SavingsGoalOut,
    SavingsGoalContribution,
    SavingsGoalUpdate,
    TransactionImportMapping,
    PasswordChange,
        PasswordChange,
        PreferencesUpdate,
        ProfileUpdate,
        SupportTicketCreate,
        SupportTicketOut,
    PreferencesUpdate,
    ProfileUpdate,
    SupportTicketCreate,
    SupportTicketOut,
)
from transaction_imports import (
    FIELD_LABELS as IMPORT_FIELD_LABELS,
    MAX_UPLOAD_BYTES,
    ImportFileError,
    parse_transaction_file,
    sample_template_bytes,
    transaction_signature,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "INR"}


async def recurring_worker(stop_event: asyncio.Event) -> None:
    """Run the recurring-transaction processor once a minute."""
    while not stop_event.is_set():
        try:
            async with SessionLocal() as db:
                await process_recurring(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not crash the API because the background recurring job failed.
            print(f"Recurring engine error: {exc}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(recurring_worker(stop_event))

    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(worker_task, timeout=5)
        except asyncio.TimeoutError:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="WealthFlow",
    version="1.0.1",
    lifespan=lifespan,
)

# Use absolute paths so the app works even when Uvicorn is started from another
# working directory.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.include_router(family_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Always convert HTTPException into a real Response object."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON instead of leaking a Python traceback to the browser."""
    import traceback

    traceback.print_exception(type(exc), exc, exc.__traceback__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"request": request},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, mode: str = "login"):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "auth_mode": "signup" if mode == "signup" else "login"},
    )


@app.get("/app", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def application_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await get_current_user(request, db)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "wealthflow"}

# -----------------------------------------------------------------------------
# Admin portal
# -----------------------------------------------------------------------------

ADMIN_COOKIE = "wealthflow_admin"


def is_admin_authenticated(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return False

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        return payload.get("role") == "admin"
    except JWTError:
        return False


@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if is_admin_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"request": request, "error": None},
    )


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    if not settings.admin_password:
        return HTMLResponse(
            "Admin login is not configured. Set ADMIN_PASSWORD in your .env file.",
            status_code=503,
        )

    form = await request.form()
    password = str(form.get("password", ""))

    if not secrets.compare_digest(password, settings.admin_password):
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"request": request, "error": "Incorrect password."},
            status_code=401,
        )

    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )

    token = jwt.encode(
        {"role": "admin", "exp": expires},
        settings.jwt_secret,
        algorithm="HS256",
    )

    response = RedirectResponse("/admin/dashboard", status_code=303)
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.jwt_expire_minutes * 60,
        path="/admin",
    )
    return response



@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_admin_authenticated(request):
        return RedirectResponse("/admin", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={"request": request},
    )


def _analytics_bucket_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@app.get("/admin/api/platform-analytics")
async def admin_platform_analytics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
):
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")

    today = date.today()
    range_end = end_date or today
    range_start = start_date or range_end - timedelta(days=29)
    if range_start > range_end:
        raise HTTPException(status_code=422, detail="Start date must be on or before end date")
    if (range_end - range_start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")

    start_at = datetime.combine(range_start, datetime.min.time(), tzinfo=timezone.utc)
    end_at = datetime.combine(range_end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    metric_statement = select(
        select(func.count()).select_from(User).scalar_subquery().label("registered_users"),
        select(func.count())
        .select_from(User)
        .where(User.created_at >= start_at, User.created_at < end_at)
        .scalar_subquery()
        .label("new_users"),
        select(func.count())
        .select_from(User)
        .where(User.created_at < start_at)
        .scalar_subquery()
        .label("users_before_range"),
        select(func.count()).select_from(Transaction).scalar_subquery().label("total_transactions"),
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.transaction_date >= range_start, Transaction.transaction_date <= range_end)
        .scalar_subquery()
        .label("period_transactions"),
        select(func.count(func.distinct(Transaction.user_id)))
        .select_from(Transaction)
        .where(Transaction.transaction_date >= range_start, Transaction.transaction_date <= range_end)
        .scalar_subquery()
        .label("active_users"),
    )
    metrics = (await db.execute(metric_statement)).one()

    registration_rows = await db.execute(
        select(func.date(User.created_at), func.count(User.id))
        .where(User.created_at >= start_at, User.created_at < end_at)
        .group_by(func.date(User.created_at))
    )
    transaction_rows = await db.execute(
        select(Transaction.transaction_date, func.count(Transaction.id))
        .where(Transaction.transaction_date >= range_start, Transaction.transaction_date <= range_end)
        .group_by(Transaction.transaction_date)
    )
    registration_counts = {
        _analytics_bucket_date(day): int(count)
        for day, count in registration_rows
    }
    transaction_counts = {
        _analytics_bucket_date(day): int(count)
        for day, count in transaction_rows
    }

    interval = "day" if (range_end - range_start).days <= 29 else "month"
    if interval == "day":
        bucket_dates = [
            range_start + timedelta(days=offset)
            for offset in range((range_end - range_start).days + 1)
        ]
        labels = [day.isoformat() for day in bucket_dates]
        new_user_series = [registration_counts.get(day, 0) for day in bucket_dates]
        transaction_series = [transaction_counts.get(day, 0) for day in bucket_dates]
    else:
        month_dates: list[date] = []
        cursor = date(range_start.year, range_start.month, 1)
        last_month = date(range_end.year, range_end.month, 1)
        while cursor <= last_month:
            month_dates.append(cursor)
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        labels = [month.strftime("%Y-%m") for month in month_dates]
        monthly_registrations: dict[date, int] = {}
        for day, count in registration_counts.items():
            month = date(day.year, day.month, 1)
            monthly_registrations[month] = monthly_registrations.get(month, 0) + count
        monthly_transactions: dict[date, int] = {}
        for day, count in transaction_counts.items():
            month = date(day.year, day.month, 1)
            monthly_transactions[month] = monthly_transactions.get(month, 0) + count
        new_user_series = [monthly_registrations.get(month, 0) for month in month_dates]
        transaction_series = [monthly_transactions.get(month, 0) for month in month_dates]

    cumulative_users = []
    running_users = int(metrics.users_before_range or 0)
    for count in new_user_series:
        running_users += count
        cumulative_users.append(running_users)

    return {
        "range": {
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
            "interval": interval,
        },
        "metrics": {
            "registered_users": int(metrics.registered_users or 0),
            "new_users": int(metrics.new_users or 0),
            "active_users": int(metrics.active_users or 0),
            "total_transactions": int(metrics.total_transactions or 0),
            "period_transactions": int(metrics.period_transactions or 0),
        },
        "series": {
            "labels": labels,
            "new_users": new_user_series,
            "cumulative_users": cumulative_users,
            "transactions": transaction_series,
        },
    }


@app.get("/admin/users", response_class=HTMLResponse) #####
async def admin_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not is_admin_authenticated(request):
        return RedirectResponse("/admin", status_code=303)

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={"request": request, "users": users},
    )

@app.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_details(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not is_admin_authenticated(request):
        return RedirectResponse("/admin", status_code=303)

    user = await db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    transaction_count = await db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == user.id)
    )

    return HTMLResponse(
        f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>WealthFlow - User Details</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="min-h-screen bg-slate-950 p-6 text-slate-100">
            <main class="mx-auto max-w-3xl">
                <a href="/admin/users"
                   class="text-indigo-400 hover:text-indigo-300">
                    &larr; Back to Registered Users
                </a>

                <h1 class="mt-6 text-3xl font-bold">User Details</h1>

                <div class="mt-6 space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
                    <p><span class="text-slate-400">User ID:</span> {user.id}</p>
                    <p><span class="text-slate-400">Full Name:</span> {escape(user.full_name)}</p>
                    <p><span class="text-slate-400">Email:</span> {escape(str(user.email))}</p>
                    <p><span class="text-slate-400">Currency:</span> {escape(user.base_currency)}</p>
                    <p><span class="text-slate-400">Registered:</span> {user.created_at}</p>
                    <p><span class="text-slate-400">Total Transactions:</span> {transaction_count or 0}</p>
                </div>
            </main>
        </body>
        </html>
        """
    )


@app.post("/admin/logout")
async def admin_logout():
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(
        key=ADMIN_COOKIE,
        path="/admin",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------


def set_auth_cookie(response: Response, user_id: int, session_version: int) -> None:
    response.set_cookie(
        "access_token",
        create_access_token(user_id, session_version),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


@app.post("/api/auth/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    data: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).lower().strip()

    exists = await db.scalar(select(User).where(User.email == email))
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        base_currency=data.base_currency.upper(),
    )

    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Profile could not be saved") from None

    set_auth_cookie(response, user.id, user.session_version)
    return user


@app.post("/api/auth/login", response_model=UserOut)
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).lower().strip()
    user = await db.scalar(select(User).where(User.email == email))

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    set_auth_cookie(response, user.id, user.session_version)
    return user


@app.post("/api/auth/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.session_version += 1
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not end the session") from None
    response.delete_cookie(
        key="access_token",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@app.get("/api/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@app.post("/api/ai/chat")
async def ai_chat(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="A message is required.")

    raw_conversation_id = payload.get("conversation_id")
    conversation_id = None
    if raw_conversation_id:
        try:
            conversation_id = UUID(str(raw_conversation_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="conversation_id must be a valid UUID") from exc

    try:
        conversation_id, answer, sections = await chat_with_ai(
            user=user,
            db=db,
            message=message,
            conversation_id=conversation_id,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback for provider issues
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail="AI request could not be processed") from exc
        raise

    return {
        "conversation_id": str(conversation_id),
        "answer": answer,
        "sections": sections,
        "suggested_questions": [
            "What did I spend most on this month?",
            "How is my budget tracking right now?",
            "Am I on track with my saving goals?",
            "What changed compared with last month?",
        ],
    }


@app.patch("/api/profile/currency", response_model=UserOut)
async def update_currency(
    currency: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    currency = currency.upper().strip()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail="Unsupported currency")

    user.base_currency = currency
    await db.commit()
    await db.refresh(user)
    return user


@app.patch("/api/settings/profile", response_model=UserOut)
async def update_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.full_name = data.full_name
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Preferences could not be saved") from None
    return user


@app.patch("/api/settings/preferences", response_model=UserOut)
async def update_preferences(
    data: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.theme = data.theme
    user.date_format = data.date_format
    user.base_currency = data.base_currency
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise
    return user


@app.post("/api/settings/password")
async def change_password(
    data: PasswordChange,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(data.new_password)
    user.session_version += 1
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Password could not be changed") from None

    response.delete_cookie(
        key="access_token",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True, "detail": "Password updated. Sign in again with your new password."}


@app.post(
    "/api/support/tickets",
    response_model=SupportTicketOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_support_ticket(
    data: SupportTicketCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = SupportTicket(
        user_id=user.id,
        subject=data.subject,
        category=data.category,
        message=data.message,
        contact_email=str(data.contact_email) if data.contact_email else None,
    )
    db.add(ticket)
    try:
        await db.commit()
        await db.refresh(ticket)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Support request could not be saved") from None
    return ticket


@app.get("/api/support/tickets", response_model=list[SupportTicketOut])
async def list_support_tickets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        .limit(50)
    )
    return result.scalars().all()


# -----------------------------------------------------------------------------
# Transactions
# -----------------------------------------------------------------------------


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def normalize_tags(tags: list[str]) -> str:
    return ",".join(
        sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})
    )


def transaction_out(tx: Transaction, user: User) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        transaction_date=tx.transaction_date,
        kind=tx.kind,
        amount=tx.amount,
        currency=tx.currency,
        amount_base=convert(tx.amount, tx.currency, user.base_currency),
        category=tx.category,
        merchant=tx.merchant,
        note=tx.note,
        tags=parse_tags(tx.tags),
    )


@app.post("/api/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = Transaction(
        user_id=user.id,
        transaction_date=data.transaction_date,
        kind=data.kind,
        amount=data.amount,
        currency=data.currency.upper(),
        category=data.category.strip(),
        merchant=data.merchant.strip(),
        note=data.note.strip(),
        tags=normalize_tags(data.tags),
    )

    db.add(tx)
    try:
        await db.commit()
        await db.refresh(tx)
    except Exception:
        await db.rollback()
        raise

    return transaction_out(tx, user)


@app.put("/api/transactions/{transaction_id}", response_model=TransactionOut)
async def update_transaction(
    transaction_id: int,
    data: TransactionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
    )

    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    tx.transaction_date = data.transaction_date
    tx.kind = data.kind
    tx.amount = data.amount
    tx.currency = data.currency.upper()
    tx.category = data.category.strip()
    tx.merchant = data.merchant.strip()
    tx.note = data.note.strip()
    tx.tags = normalize_tags(data.tags)

    try:
        await db.commit()
        await db.refresh(tx)
    except Exception:
        await db.rollback()
        raise

    return transaction_out(tx, user)


@app.get("/api/transactions", response_model=list[TransactionOut])
async def list_transactions(
    q: str | None = None,
    kind: str | None = None,
    categories: str | None = None,
    tags: str | None = None,
    min_amount: Decimal | None = Query(default=None, ge=0),
    max_amount: Decimal | None = Query(default=None, ge=0),
    start_date: date | None = None,
    end_date: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(status_code=400, detail="min_amount cannot exceed max_amount")

    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    filters = [Transaction.user_id == user.id]

    if kind:
        kind = kind.lower().strip()
        if kind not in {"income", "expense"}:
            raise HTTPException(status_code=400, detail="kind must be income or expense")
        filters.append(Transaction.kind == kind)

    if categories:
        cats = [x.strip() for x in categories.split(",") if x.strip()]
        if cats:
            filters.append(Transaction.category.in_(cats))

    if start_date:
        filters.append(Transaction.transaction_date >= start_date)
    if end_date:
        filters.append(Transaction.transaction_date <= end_date)

    if q:
        needle = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Transaction.note).like(needle),
                func.lower(Transaction.merchant).like(needle),
                func.lower(Transaction.category).like(needle),
            )
        )

    result = await db.execute(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .limit(1000)
    )

    requested_tags = [x.strip().lower() for x in tags.split(",") if x.strip()] if tags else []
    output: list[TransactionOut] = []

    for tx in result.scalars().all():
        base_amount = convert(tx.amount, tx.currency, user.base_currency)

        if min_amount is not None and base_amount < min_amount:
            continue
        if max_amount is not None and base_amount > max_amount:
            continue

        tx_tags = parse_tags(tx.tags)
        if requested_tags and not set(requested_tags).issubset(set(tx_tags)):
            continue

        output.append(transaction_out(tx, user))

    return output


@app.delete("/api/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
    )

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await db.delete(tx)
    await db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------------
# Budgets
# -----------------------------------------------------------------------------


@app.post("/api/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_budget(
    data: BudgetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    budget = await db.scalar(
        select(Budget).where(
            Budget.user_id == user.id,
            Budget.category == data.category,
            Budget.month == data.month,
            Budget.year == data.year,
        )
    )

    if budget:
        budget.amount = data.amount
    else:
        budget = Budget(user_id=user.id, **data.model_dump())
        db.add(budget)

    try:
        await db.commit()
        await db.refresh(budget)
    except Exception:
        await db.rollback()
        raise

    return budget


@app.get("/api/budgets", response_model=list[BudgetOut])
async def list_budgets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Budget)
        .where(Budget.user_id == user.id)
        .order_by(Budget.year.desc(), Budget.month.desc(), Budget.category.asc())
    )
    return result.scalars().all()


async def record_net_worth_snapshot(db: AsyncSession, user_id: int) -> None:
    result = await db.execute(
        select(NetWorthItem).where(NetWorthItem.user_id == user_id)
    )
    items = result.scalars().all()
    total_assets = sum(
        (convert(item.amount, item.currency, "USD") for item in items if item.kind == "asset"),
        Decimal("0.00"),
    )
    total_liabilities = sum(
        (convert(item.amount, item.currency, "USD") for item in items if item.kind == "liability"),
        Decimal("0.00"),
    )
    snapshot = {
        "user_id": user_id,
        "snapshot_date": date.today(),
        "total_assets_usd": total_assets,
        "total_liabilities_usd": total_liabilities,
        "net_worth_usd": total_assets - total_liabilities,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(NetWorthSnapshot).values(**snapshot)
    elif dialect == "postgresql":
        statement = postgresql_insert(NetWorthSnapshot).values(**snapshot)
    else:
        raise RuntimeError(f"Net worth snapshots do not support database dialect: {dialect}")

    await db.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id", "snapshot_date"],
            set_={
                "total_assets_usd": snapshot["total_assets_usd"],
                "total_liabilities_usd": snapshot["total_liabilities_usd"],
                "net_worth_usd": snapshot["net_worth_usd"],
            },
        )
    )


async def net_worth_summary(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    item_result = await db.execute(
        select(NetWorthItem)
        .where(NetWorthItem.user_id == user.id)
        .order_by(NetWorthItem.kind.asc(), NetWorthItem.category.asc(), NetWorthItem.name.asc())
    )
    items = item_result.scalars().all()
    item_outputs = [
        NetWorthItemOut(
            id=item.id,
            kind=item.kind,
            name=item.name,
            category=item.category,
            amount=item.amount,
            currency=item.currency,
            amount_base=convert(item.amount, item.currency, user.base_currency),
            updated_at=item.updated_at,
        )
        for item in items
    ]
    assets = [item for item in item_outputs if item.kind == "asset"]
    liabilities = [item for item in item_outputs if item.kind == "liability"]
    total_assets = sum((item.amount_base for item in assets), Decimal("0.00"))
    total_liabilities = sum((item.amount_base for item in liabilities), Decimal("0.00"))

    history_result = await db.execute(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user.id)
        .order_by(NetWorthSnapshot.snapshot_date.asc())
    )
    history = [
        NetWorthSnapshotOut(
            snapshot_date=snapshot.snapshot_date,
            total_assets=convert(snapshot.total_assets_usd, "USD", user.base_currency),
            total_liabilities=convert(snapshot.total_liabilities_usd, "USD", user.base_currency),
            net_worth=convert(snapshot.net_worth_usd, "USD", user.base_currency),
        )
        for snapshot in history_result.scalars().all()
    ]

    return {
        "base_currency": user.base_currency,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "assets": [item.model_dump() for item in assets],
        "liabilities": [item.model_dump() for item in liabilities],
        "history": [item.model_dump() for item in history],
    }


@app.get("/api/net-worth", response_model=NetWorthSummaryOut)
async def get_net_worth(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await net_worth_summary(db, user)


@app.post(
    "/api/net-worth/items",
    response_model=NetWorthItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_net_worth_item(
    data: NetWorthItemInput,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = NetWorthItem(user_id=user.id, **data.model_dump())
    db.add(item)
    try:
        await db.flush()
        await record_net_worth_snapshot(db, user.id)
        await db.commit()
        await db.refresh(item)
    except Exception:
        await db.rollback()
        raise

    return NetWorthItemOut(
        id=item.id,
        kind=item.kind,
        name=item.name,
        category=item.category,
        amount=item.amount,
        currency=item.currency,
        amount_base=convert(item.amount, item.currency, user.base_currency),
        updated_at=item.updated_at,
    )


async def get_owned_net_worth_item(
    item_id: int,
    user: User,
    db: AsyncSession,
) -> NetWorthItem | None:
    return await db.scalar(
        select(NetWorthItem).where(
            NetWorthItem.id == item_id,
            NetWorthItem.user_id == user.id,
        )
    )


@app.put("/api/net-worth/items/{item_id}", response_model=NetWorthItemOut)
async def update_net_worth_item(
    item_id: int,
    data: NetWorthItemInput,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_owned_net_worth_item(item_id, user, db)
    if item is None:
        raise HTTPException(status_code=404, detail="Net worth item not found")

    for field, value in data.model_dump().items():
        setattr(item, field, value)
    try:
        await db.flush()
        await record_net_worth_snapshot(db, user.id)
        await db.commit()
        await db.refresh(item)
    except Exception:
        await db.rollback()
        raise

    return NetWorthItemOut(
        id=item.id,
        kind=item.kind,
        name=item.name,
        category=item.category,
        amount=item.amount,
        currency=item.currency,
        amount_base=convert(item.amount, item.currency, user.base_currency),
        updated_at=item.updated_at,
    )


@app.delete("/api/net-worth/items/{item_id}")
async def delete_net_worth_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_owned_net_worth_item(item_id, user, db)
    if item is None:
        raise HTTPException(status_code=404, detail="Net worth item not found")

    try:
        await db.delete(item)
        await db.flush()
        await record_net_worth_snapshot(db, user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"ok": True}


@app.post(
    "/api/savings-goals",
    response_model=SavingsGoalOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_savings_goal(
    data: SavingsGoalCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = SavingsGoal(
        user_id=user.id,
        name=data.name,
        target_amount=data.target_amount,
        saved_amount=data.saved_amount,
        currency=data.currency,
        deadline=data.deadline,
        description=data.description,
    )
    db.add(goal)

    try:
        await db.commit()
        await db.refresh(goal)
    except Exception:
        await db.rollback()
        raise

    return goal


@app.get(
    "/api/savings-goals",
    response_model=list[SavingsGoalOut],
)
async def list_savings_goals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavingsGoal)
        .where(SavingsGoal.user_id == user.id)
        .order_by(SavingsGoal.created_at.desc())
    )
    return result.scalars().all()


async def get_owned_savings_goal(
    goal_id: int,
    user: User,
    db: AsyncSession,
) -> SavingsGoal | None:
    return await db.scalar(
        select(SavingsGoal).where(
            SavingsGoal.id == goal_id,
            SavingsGoal.user_id == user.id,
        )
    )


@app.put(
    "/api/savings-goals/{goal_id}",
    response_model=SavingsGoalOut,
)
async def update_savings_goal(
    goal_id: int,
    data: SavingsGoalUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await get_owned_savings_goal(goal_id, user, db)
    if goal is None:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    if data.currency != goal.currency and goal.saved_amount > 0:
        raise HTTPException(
            status_code=409,
            detail="Currency cannot be changed after money has been saved",
        )

    result = await db.execute(
        update(SavingsGoal)
        .where(
            SavingsGoal.id == goal_id,
            SavingsGoal.user_id == user.id,
            SavingsGoal.saved_amount <= data.target_amount,
            or_(SavingsGoal.currency == data.currency, SavingsGoal.saved_amount == 0),
        )
        .values(
            name=data.name,
            target_amount=data.target_amount,
            currency=data.currency,
            deadline=data.deadline,
            description=data.description,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        if data.currency != goal.currency and goal.saved_amount > 0:
            detail = "Currency cannot be changed after money has been saved"
        else:
            detail = "Target amount cannot be less than the amount already saved"
        raise HTTPException(
            status_code=409,
            detail=detail,
        )

    try:
        await db.commit()
        await db.refresh(goal)
    except Exception:
        await db.rollback()
        raise

    return goal


@app.delete("/api/savings-goals/{goal_id}")
async def delete_savings_goal(
    goal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await get_owned_savings_goal(goal_id, user, db)
    if goal is None:
        raise HTTPException(status_code=404, detail="Savings goal not found")

    try:
        await db.delete(goal)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"ok": True}


@app.post(
    "/api/savings-goals/{goal_id}/contribute",
    response_model=SavingsGoalOut,
)
async def contribute_to_savings_goal(
    goal_id: int,
    data: SavingsGoalContribution,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await get_owned_savings_goal(goal_id, user, db)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Savings goal not found",
        )

    if data.amount > goal.target_amount:
        raise HTTPException(status_code=409, detail="Contribution exceeds the remaining amount")

    try:
        result = await db.execute(
            update(SavingsGoal)
            .where(
                SavingsGoal.id == goal_id,
                SavingsGoal.user_id == user.id,
                SavingsGoal.saved_amount + data.amount <= SavingsGoal.target_amount,
            )
            .values(saved_amount=SavingsGoal.saved_amount + data.amount)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=409, detail="Contribution exceeds the remaining amount")
        await db.commit()
        await db.refresh(goal)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return goal


@app.post(
    "/api/savings-goals/{goal_id}/withdraw",
    response_model=SavingsGoalOut,
)
async def withdraw_from_savings_goal(
    goal_id: int,
    data: SavingsGoalContribution,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await get_owned_savings_goal(goal_id, user, db)
    if goal is None:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    if data.amount > goal.saved_amount:
        raise HTTPException(status_code=400, detail="Withdrawal exceeds the saved amount")

    try:
        result = await db.execute(
            update(SavingsGoal)
            .where(
                SavingsGoal.id == goal_id,
                SavingsGoal.user_id == user.id,
                SavingsGoal.saved_amount >= data.amount,
            )
            .values(saved_amount=SavingsGoal.saved_amount - data.amount)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=400, detail="Withdrawal exceeds the saved amount")
        await db.commit()
        await db.refresh(goal)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return goal




# -----------------------------------------------------------------------------
# Recurring transactions
# -----------------------------------------------------------------------------


@app.post("/api/recurring", response_model=RecurringOut, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    data: RecurringCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = RecurringTransaction(
        user_id=user.id,
        name=data.name.strip(),
        kind=data.kind,
        amount=data.amount,
        currency=data.currency.upper(),
        category=data.category.strip(),
        frequency=data.frequency,
        next_due=data.next_due,
        active=data.active,
    )

    db.add(item)
    try:
        await db.commit()
        await db.refresh(item)
    except Exception:
        await db.rollback()
        raise

    return item


@app.get("/api/recurring", response_model=list[RecurringOut])
async def list_recurring(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RecurringTransaction)
        .where(RecurringTransaction.user_id == user.id)
        .order_by(RecurringTransaction.next_due.asc(), RecurringTransaction.id.asc())
    )
    return result.scalars().all()


@app.delete("/api/recurring/{recurring_id}")
async def delete_recurring(
    recurring_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(
        select(RecurringTransaction).where(
            RecurringTransaction.id == recurring_id,
            RecurringTransaction.user_id == user.id,
        )
    )

    if not item:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    # Keep history intact; deactivate the recurring rule instead of deleting it.
    item.active = False
    await db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------------
# Analytics and exports
# -----------------------------------------------------------------------------


def _import_digest(content: bytes, mapping: dict[str, str]) -> str:
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(json.dumps(mapping, sort_keys=True, ensure_ascii=True).encode("utf-8"))
    return digest.hexdigest()


def _import_confirmation_token(user_id: int, request_id: UUID, digest: str) -> str:
    message = f"{user_id}:{request_id}:{digest}".encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


async def _read_import_upload(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    await upload.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Files must be 5 MB or smaller")
    return content


def _mapping_from_json(mapping_json: str) -> dict[str, str]:
    try:
        mapping = TransactionImportMapping.model_validate_json(mapping_json or "{}").model_dump(exclude_none=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid column mapping: {exc}") from None
    return {field: header.strip() for field, header in mapping.items() if header.strip()}


async def _existing_transaction_signatures(
    db: AsyncSession,
    user: User,
    rows: list[dict[str, Any]],
) -> set[tuple[Any, ...]]:
    dates = sorted({date.fromisoformat(row["values"]["transaction_date"]) for row in rows if row["valid"]})
    signatures: set[tuple[Any, ...]] = set()
    for offset in range(0, len(dates), 300):
        result = await db.execute(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.transaction_date.in_(dates[offset:offset + 300]),
            )
        )
        for transaction in result.scalars().all():
            signatures.add(transaction_signature({
                "transaction_date": transaction.transaction_date.isoformat(),
                "kind": transaction.kind,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "category": transaction.category,
                "merchant": transaction.merchant,
                "note": transaction.note,
                "tags": parse_tags(transaction.tags),
            }))
    return signatures


async def _mark_import_duplicates(
    preview: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    existing = await _existing_transaction_signatures(db, user, preview["rows"])
    seen_in_file: set[tuple[Any, ...]] = set()
    duplicate_count = 0
    for row in preview["rows"]:
        if not row["valid"]:
            continue
        signature = transaction_signature(row["values"])
        if signature in existing:
            row["possible_duplicate"] = True
            row["duplicate_reason"] = "Matches an existing transaction in your account"
        elif signature in seen_in_file:
            row["possible_duplicate"] = True
            row["duplicate_reason"] = "Duplicates another row in this file"
        seen_in_file.add(signature)
        if row["possible_duplicate"]:
            duplicate_count += 1
    preview["summary"]["possible_duplicates"] = duplicate_count
    return preview


@app.get("/api/transactions/import/template")
async def download_transaction_import_template(
    user: User = Depends(get_current_user),
):
    del user
    return StreamingResponse(
        iter([sample_template_bytes()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=wealthflow-transaction-template.xlsx",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/transactions/import/preview")
async def preview_transaction_import(
    upload: UploadFile = File(...),
    mapping_json: str = Form(default="{}"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id
    content = await _read_import_upload(upload)
    mapping = _mapping_from_json(mapping_json)
    try:
        preview = parse_transaction_file(upload.filename or "", content, mapping or None)
    except ImportFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    preview = await _mark_import_duplicates(preview, db, user)
    request_id = uuid4()
    digest = _import_digest(content, mapping)
    preview["request_id"] = str(request_id)
    preview["confirmation_token"] = _import_confirmation_token(user_id, request_id, digest)
    preview["mapping"] = mapping
    return preview


@app.post("/api/transactions/import/confirm")
async def confirm_transaction_import(
    upload: UploadFile = File(...),
    request_id: UUID = Form(...),
    confirmation_token: str = Form(...),
    mapping_json: str = Form(default="{}"),
    import_valid_only: bool = Form(default=False),
    include_duplicates: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id
    content = await _read_import_upload(upload)
    mapping = _mapping_from_json(mapping_json)
    try:
        preview = parse_transaction_file(upload.filename or "", content, mapping or None)
    except ImportFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    digest = _import_digest(content, mapping)
    expected_token = _import_confirmation_token(user_id, request_id, digest)
    if not hmac.compare_digest(confirmation_token, expected_token):
        raise HTTPException(status_code=409, detail="The preview confirmation is invalid or the file changed; preview it again")

    batch = await db.scalar(
        select(TransactionImportBatch).where(
            TransactionImportBatch.user_id == user_id,
            TransactionImportBatch.request_id == str(request_id),
        )
    )
    if batch is not None:
        if batch.content_digest != digest:
            raise HTTPException(status_code=409, detail="This request ID was already used for a different file")
        previous = json.loads(batch.result_json)
        if previous.get("state") == "complete":
            return previous["result"]

    if batch is None:
        batch = TransactionImportBatch(
            user_id=user_id,
            request_id=str(request_id),
            content_digest=digest,
            result_json="{}",
        )
        db.add(batch)

    preview = await _mark_import_duplicates(preview, db, user)
    invalid_rows = [row for row in preview["rows"] if not row["valid"]]
    if invalid_rows and not import_valid_only:
        raise HTTPException(
            status_code=422,
            detail="The file has invalid rows. Choose import valid rows only, or correct the file and preview it again.",
        )

    existing_signatures = await _existing_transaction_signatures(db, user, preview["rows"])
    seen_signatures: set[tuple[Any, ...]] = set()
    transactions: list[Transaction] = []
    result_rows: list[dict[str, Any]] = []
    skipped_duplicates = 0
    included_duplicates = 0

    for row in preview["rows"]:
        if not row["valid"]:
            result_rows.append({
                "row_number": row["row_number"],
                "status": "skipped_invalid",
                "reason": "; ".join(row["errors"]),
            })
            continue

        values = row["values"]
        signature = transaction_signature(values)
        is_duplicate = signature in existing_signatures or signature in seen_signatures
        seen_signatures.add(signature)
        if is_duplicate and not include_duplicates:
            skipped_duplicates += 1
            result_rows.append({
                "row_number": row["row_number"],
                "status": "skipped_duplicate",
                "reason": row["duplicate_reason"] or "Matches a transaction already selected in this import",
            })
            continue
        if is_duplicate:
            included_duplicates += 1

        transactions.append(Transaction(
            user_id=user_id,
            transaction_date=date.fromisoformat(values["transaction_date"]),
            kind=values["kind"],
            amount=Decimal(values["amount"]),
            currency=values["currency"],
            category=values["category"],
            merchant=values["merchant"],
            note=values["note"],
            tags=normalize_tags(values["tags"]),
        ))
        result_rows.append({"row_number": row["row_number"], "status": "imported", "reason": ""})

    result_payload = {
        "request_id": str(request_id),
        "total_rows": len(preview["rows"]),
        "imported": len(transactions),
        "invalid_skipped": len(invalid_rows),
        "duplicate_skipped": skipped_duplicates,
        "duplicates_included": included_duplicates,
        "rows": result_rows,
    }
    try:
        db.add_all(transactions)
        batch.result_json = json.dumps({"state": "complete", "result": result_payload})
        await db.commit()
    except IntegrityError:
        await db.rollback()
        previous_batch = await db.scalar(
            select(TransactionImportBatch).where(
                TransactionImportBatch.user_id == user_id,
                TransactionImportBatch.request_id == str(request_id),
            )
        )
        if previous_batch and previous_batch.content_digest == digest:
            previous_result = json.loads(previous_batch.result_json)
            if previous_result.get("state") == "complete":
                return previous_result["result"]
        raise HTTPException(status_code=409, detail="This import was submitted concurrently; check the import result") from None
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Import failed and no transactions were saved") from None

    return result_payload


@app.get("/api/transactions/import/{request_id}/errors")
async def download_transaction_import_errors(
    request_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await db.scalar(
        select(TransactionImportBatch).where(
            TransactionImportBatch.user_id == user.id,
            TransactionImportBatch.request_id == str(request_id),
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Import result not found")

    stored = json.loads(batch.result_json)
    if stored.get("state") != "complete":
        raise HTTPException(status_code=409, detail="This import has not been confirmed")

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["row_number", "status", "reason"])
    writer.writeheader()
    writer.writerows(
        row for row in stored["result"]["rows"]
        if row["status"] != "imported"
    )
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=wealthflow-import-errors-{request_id}.csv",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/analytics")
async def analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_analytics(db, user)


@app.get("/api/export/{fmt}")
async def export_data(
    fmt: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fmt = fmt.lower().strip()
    rows = await get_export_rows(db, user)

    if fmt == "csv":
        data = csv_bytes(rows)
        return StreamingResponse(
            iter([data]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=wealthflow-transactions.csv",
                "X-Content-Type-Options": "nosniff",
            },
        )

    if fmt == "xlsx":
        data = xlsx_bytes(rows)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=wealthflow-transactions.xlsx",
                "X-Content-Type-Options": "nosniff",
            },
        )

    raise HTTPException(status_code=400, detail="Format must be csv or xlsx")


@app.get("/api/fx")
async def fx():
    return {
        "USD": 1,
        "EUR": 1.08,
        "GBP": 1.27,
        "INR": 0.0120,
    }

####################################################
