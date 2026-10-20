from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from currency import convert
from database import get_db
from models import (
    Family,
    FamilyBudget,
    FamilyExpense,
    FamilyInvitation,
    FamilyMember,
    FamilyNotification,
    FamilySavingsContribution,
    FamilySavingsGoal,
    Transaction,
    User,
)
from schemas import CURRENCIES


router = APIRouter(prefix="/api", tags=["family"])


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Family name cannot be blank")
        return value


class InvitationCreate(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class FamilySettingsUpdate(BaseModel):
    share_financial_summary: bool | None = None
    notifications_enabled: bool | None = None
    members_can_manage_resources: bool | None = None

    @model_validator(mode="after")
    def require_setting(self):
        if all(
            value is None
            for value in (
                self.share_financial_summary,
                self.notifications_enabled,
                self.members_can_manage_resources,
            )
        ):
            raise ValueError("Choose at least one setting to update")
        return self


class LeaveFamilyRequest(BaseModel):
    transfer_to_user_id: int | None = Field(default=None, gt=0)


class FamilyBudgetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "USD"
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)

    @field_validator("category")
    @classmethod
    def nonblank_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class FamilyExpenseCreate(BaseModel):
    transaction_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    description: str = Field(default="", max_length=200)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return value.strip()


class FamilyGoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "USD"
    deadline: date | None = None
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Goal name cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return value.strip()


class FamilyContribution(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class InvitationResponse(BaseModel):
    action: Literal["accept", "decline"]


async def get_family_membership(
    family_id: int,
    user: User,
    db: AsyncSession,
) -> tuple[Family, FamilyMember]:
    membership = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Family not found")
    family = await db.get(Family, family_id)
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")
    return family, membership


def require_owner(family: Family, membership: FamilyMember) -> None:
    if membership.role != "owner" or family.owner_user_id != membership.user_id:
        raise HTTPException(status_code=403, detail="Only the family owner can do this")


def require_resource_manager(family: Family, membership: FamilyMember) -> None:
    if membership.role != "owner" and not family.members_can_manage_resources:
        raise HTTPException(status_code=403, detail="The family owner has restricted shared-resource management")


def family_summary(family: Family, membership: FamilyMember | None = None) -> dict:
    result = {
        "id": family.id,
        "name": family.name,
        "owner_user_id": family.owner_user_id,
        "members_can_manage_resources": family.members_can_manage_resources,
        "created_at": family.created_at,
    }
    if membership is not None:
        result.update({
            "role": membership.role,
            "share_financial_summary": membership.share_financial_summary,
            "notifications_enabled": membership.notifications_enabled,
        })
    return result


async def add_family_notifications(
    db: AsyncSession,
    family_id: int,
    actor_user_id: int,
    message: str,
) -> None:
    result = await db.execute(
        select(FamilyMember.user_id).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id != actor_user_id,
            FamilyMember.notifications_enabled.is_(True),
        )
    )
    db.add_all(
        FamilyNotification(
            family_id=family_id,
            recipient_user_id=user_id,
            message=message,
        )
        for user_id in result.scalars().all()
    )


async def get_family_budget_summaries(db: AsyncSession, family_id: int) -> list[dict]:
    result = await db.execute(
        select(FamilyBudget)
        .where(FamilyBudget.family_id == family_id)
        .order_by(FamilyBudget.year.desc(), FamilyBudget.month.desc(), FamilyBudget.category.asc())
    )
    budgets = result.scalars().all()
    summaries = []
    for budget in budgets:
        spent = await db.scalar(
            select(func.coalesce(func.sum(FamilyExpense.amount), 0)).where(
                FamilyExpense.family_id == family_id,
                FamilyExpense.budget_id == budget.id,
            )
        )
        spent_amount = Decimal(spent or 0)
        amount = Decimal(budget.amount)
        summaries.append({
            "id": budget.id,
            "category": budget.category,
            "amount": amount,
            "currency": budget.currency,
            "month": budget.month,
            "year": budget.year,
            "spent_amount": spent_amount,
            "remaining_amount": max(Decimal("0"), amount - spent_amount),
            "progress_percentage": min(
                Decimal("100"),
                (spent_amount / amount * Decimal("100")).quantize(Decimal("0.1")),
            ),
        })
    return summaries


async def get_family_goal_summaries(db: AsyncSession, family_id: int) -> list[dict]:
    result = await db.execute(
        select(FamilySavingsGoal)
        .where(FamilySavingsGoal.family_id == family_id)
        .order_by(FamilySavingsGoal.created_at.desc())
    )
    summaries = []
    for goal in result.scalars().all():
        saved = Decimal(goal.saved_amount)
        target = Decimal(goal.target_amount)
        summaries.append({
            "id": goal.id,
            "name": goal.name,
            "target_amount": target,
            "saved_amount": saved,
            "currency": goal.currency,
            "deadline": goal.deadline,
            "description": goal.description,
            "remaining_amount": max(Decimal("0"), target - saved),
            "progress_percentage": min(
                Decimal("100"),
                (saved / target * Decimal("100")).quantize(Decimal("0.1")),
            ),
        })
    return summaries


@router.post("/families", status_code=status.HTTP_201_CREATED)
async def create_family(
    data: FamilyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family = Family(name=data.name, owner_user_id=user.id)
    db.add(family)
    await db.flush()
    membership = FamilyMember(family_id=family.id, user_id=user.id, role="owner")
    db.add(membership)
    await db.commit()
    await db.refresh(family)
    return family_summary(family, membership)


@router.get("/families")
async def list_families(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Family, FamilyMember)
        .join(FamilyMember, FamilyMember.family_id == Family.id)
        .where(FamilyMember.user_id == user.id)
        .order_by(Family.created_at.desc())
    )
    families = []
    for family, membership in result.all():
        count = await db.scalar(
            select(func.count(FamilyMember.id)).where(FamilyMember.family_id == family.id)
        )
        summary = family_summary(family, membership)
        summary["member_count"] = count or 0
        families.append(summary)
    return families


@router.get("/family-invitations")
async def list_my_family_invitations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyInvitation, Family)
        .join(Family, Family.id == FamilyInvitation.family_id)
        .where(
            func.lower(FamilyInvitation.email) == user.email.lower(),
            FamilyInvitation.status == "pending",
        )
        .order_by(FamilyInvitation.created_at.desc())
    )
    return [
        {
            "id": invitation.id,
            "family_id": family.id,
            "family_name": family.name,
            "invited_at": invitation.created_at,
        }
        for invitation, family in result.all()
    ]


@router.post("/family-invitations/{invitation_id}/respond")
async def respond_to_family_invitation(
    invitation_id: int,
    data: InvitationResponse,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invitation = await db.get(FamilyInvitation, invitation_id)
    if (
        invitation is None
        or invitation.status != "pending"
        or invitation.email.lower() != user.email.lower()
    ):
        raise HTTPException(status_code=404, detail="Invitation not found")

    if data.action == "accept":
        family = await db.get(Family, invitation.family_id)
        if family is None:
            raise HTTPException(status_code=404, detail="Family not found")
        existing = await db.scalar(
            select(FamilyMember).where(
                FamilyMember.family_id == invitation.family_id,
                FamilyMember.user_id == user.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="You are already a family member")
        db.add(FamilyMember(family_id=invitation.family_id, user_id=user.id, role="member"))
        await add_family_notifications(
            db, family.id, user.id, f"{user.full_name} joined the family"
        )
    invitation.status = "accepted" if data.action == "accept" else "declined"
    invitation.responded_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="You are already a family member") from exc
    return {"ok": True, "status": invitation.status}


@router.get("/families/{family_id}")
async def get_family(
    family_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    result = await db.execute(
        select(FamilyMember, User.full_name, User.email)
        .join(User, User.id == FamilyMember.user_id)
        .where(FamilyMember.family_id == family_id)
        .order_by(FamilyMember.role.desc(), User.full_name.asc())
    )
    members = [
        {
            "user_id": member.user_id,
            "full_name": full_name,
            "email": email,
            "role": member.role,
            "share_financial_summary": member.share_financial_summary,
            "joined_at": member.joined_at,
        }
        for member, full_name, email in result.all()
    ]
    return {**family_summary(family, membership), "members": members}


@router.patch("/families/{family_id}/settings")
async def update_family_settings(
    family_id: int,
    data: FamilySettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)

    if "members_can_manage_resources" in changes:
        require_owner(family, membership)
        family.members_can_manage_resources = changes.pop("members_can_manage_resources")
    if "share_financial_summary" in changes:
        membership.share_financial_summary = changes.pop("share_financial_summary")
    if "notifications_enabled" in changes:
        membership.notifications_enabled = changes.pop("notifications_enabled")

    await db.commit()
    return family_summary(family, membership)


@router.post("/families/{family_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_family_invitation(
    family_id: int,
    data: InvitationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_owner(family, membership)
    if data.email == user.email.lower():
        raise HTTPException(status_code=409, detail="You are already the family owner")

    invited_user = await db.scalar(select(User).where(func.lower(User.email) == data.email))
    if invited_user is not None:
        existing_member = await db.scalar(
            select(FamilyMember).where(
                FamilyMember.family_id == family_id,
                FamilyMember.user_id == invited_user.id,
            )
        )
        if existing_member:
            raise HTTPException(status_code=409, detail="This person is already a family member")

    invitation = await db.scalar(
        select(FamilyInvitation).where(
            FamilyInvitation.family_id == family_id,
            FamilyInvitation.email == data.email,
        )
    )
    if invitation is not None and invitation.status == "pending":
        raise HTTPException(status_code=409, detail="An invitation is already pending")
    if invitation is None:
        invitation = FamilyInvitation(
            family_id=family_id,
            email=data.email,
            invited_by_user_id=user.id,
        )
        db.add(invitation)
    else:
        invitation.invited_by_user_id = user.id
        invitation.status = "pending"
        invitation.created_at = datetime.now(timezone.utc)
        invitation.responded_at = None
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An invitation already exists for this email") from exc
    await db.refresh(invitation)
    return {"id": invitation.id, "email": invitation.email, "status": invitation.status}


@router.get("/families/{family_id}/invitations")
async def list_family_invitations(
    family_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_owner(family, membership)
    result = await db.execute(
        select(FamilyInvitation)
        .where(FamilyInvitation.family_id == family_id)
        .order_by(FamilyInvitation.created_at.desc())
    )
    return [
        {"id": item.id, "email": item.email, "status": item.status, "created_at": item.created_at}
        for item in result.scalars().all()
    ]


@router.delete("/families/{family_id}/invitations/{invitation_id}")
async def cancel_family_invitation(
    family_id: int,
    invitation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_owner(family, membership)
    invitation = await db.scalar(
        select(FamilyInvitation).where(
            FamilyInvitation.id == invitation_id,
            FamilyInvitation.family_id == family_id,
            FamilyInvitation.status == "pending",
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    invitation.status = "canceled"
    invitation.responded_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.delete("/families/{family_id}/members/{member_user_id}")
async def remove_family_member(
    family_id: int,
    member_user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_owner(family, membership)
    if member_user_id == family.owner_user_id:
        raise HTTPException(status_code=409, detail="The family owner cannot remove themselves")
    member = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == member_user_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Family member not found")
    await db.delete(member)
    await db.commit()
    return {"ok": True}


@router.post("/families/{family_id}/leave")
async def leave_family(
    family_id: int,
    data: LeaveFamilyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    if membership.role == "owner":
        require_owner(family, membership)
        member_ids = list(
            (
                await db.scalars(
                    select(FamilyMember.user_id).where(
                        FamilyMember.family_id == family_id,
                        FamilyMember.user_id != user.id,
                    )
                )
            ).all()
        )
        if member_ids:
            successor_id = data.transfer_to_user_id
            if successor_id not in member_ids:
                raise HTTPException(
                    status_code=409,
                    detail="Choose an existing family member to become the new owner before leaving",
                )
            successor = await db.scalar(
                select(FamilyMember).where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.user_id == successor_id,
                )
            )
            family.owner_user_id = successor_id
            successor.role = "owner"
        else:
            for model in (
                FamilyNotification,
                FamilyExpense,
                FamilySavingsContribution,
                FamilySavingsGoal,
                FamilyBudget,
                FamilyInvitation,
                FamilyMember,
            ):
                if model is FamilySavingsContribution:
                    statement = delete(model).where(
                        model.goal_id.in_(
                            select(FamilySavingsGoal.id).where(
                                FamilySavingsGoal.family_id == family_id
                            )
                        )
                    )
                else:
                    statement = delete(model).where(model.family_id == family_id)
                await db.execute(statement)
            await db.delete(family)
            await db.commit()
            return {"ok": True, "family_deleted": True}

    await db.delete(membership)
    await db.commit()
    return {"ok": True, "family_deleted": False}

@router.post("/families/{family_id}/budgets", status_code=status.HTTP_201_CREATED)
async def create_family_budget(
    family_id: int,
    data: FamilyBudgetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_resource_manager(family, membership)
    budget = FamilyBudget(
        family_id=family_id,
        created_by_user_id=user.id,
        **data.model_dump(),
    )
    db.add(budget)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_family_budget_period" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A budget already exists for this category and period") from exc
        raise
    await add_family_notifications(
        db, family_id, user.id, f"{user.full_name} created a shared {data.category} budget"
    )
    await db.commit()
    await db.refresh(budget)
    return {"id": budget.id, **data.model_dump()}


@router.post("/families/{family_id}/budgets/{budget_id}/expenses", status_code=status.HTTP_201_CREATED)
async def add_family_expense(
    family_id: int,
    budget_id: int,
    data: FamilyExpenseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_family_membership(family_id, user, db)
    budget = await db.scalar(
        select(FamilyBudget).where(
            FamilyBudget.id == budget_id,
            FamilyBudget.family_id == family_id,
        )
    )
    if budget is None:
        raise HTTPException(status_code=404, detail="Shared budget not found")
    if data.transaction_date.month != budget.month or data.transaction_date.year != budget.year:
        raise HTTPException(status_code=422, detail="Expense date must be within the budget month")
    expense = FamilyExpense(
        family_id=family_id,
        budget_id=budget_id,
        created_by_user_id=user.id,
        transaction_date=data.transaction_date,
        amount=data.amount,
        currency=budget.currency,
        description=data.description,
    )
    db.add(expense)
    await add_family_notifications(
        db, family_id, user.id, f"{user.full_name} added to the shared {budget.category} budget"
    )
    await db.commit()
    return {"ok": True, "id": expense.id}


@router.post("/families/{family_id}/goals", status_code=status.HTTP_201_CREATED)
async def create_family_goal(
    family_id: int,
    data: FamilyGoalCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    require_resource_manager(family, membership)
    goal = FamilySavingsGoal(
        family_id=family_id,
        created_by_user_id=user.id,
        **data.model_dump(),
    )
    db.add(goal)
    await db.flush()
    await add_family_notifications(
        db, family_id, user.id, f"{user.full_name} created a shared savings goal"
    )
    await db.commit()
    await db.refresh(goal)
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "saved_amount": goal.saved_amount,
        "currency": goal.currency,
        "deadline": goal.deadline,
        "description": goal.description,
    }


@router.post("/families/{family_id}/goals/{goal_id}/contributions", status_code=status.HTTP_201_CREATED)
async def contribute_to_family_goal(
    family_id: int,
    goal_id: int,
    data: FamilyContribution,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_family_membership(family_id, user, db)
    goal = await db.scalar(
        select(FamilySavingsGoal).where(
            FamilySavingsGoal.id == goal_id,
            FamilySavingsGoal.family_id == family_id,
        )
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Shared savings goal not found")
    result = await db.execute(
        update(FamilySavingsGoal)
        .where(
            FamilySavingsGoal.id == goal_id,
            FamilySavingsGoal.family_id == family_id,
            FamilySavingsGoal.saved_amount + data.amount <= FamilySavingsGoal.target_amount,
        )
        .values(saved_amount=FamilySavingsGoal.saved_amount + data.amount)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Contribution exceeds the goal's remaining amount")
    db.add(
        FamilySavingsContribution(
            goal_id=goal_id,
            contributed_by_user_id=user.id,
            amount=data.amount,
        )
    )
    await add_family_notifications(
        db, family_id, user.id, f"{user.full_name} contributed to a shared savings goal"
    )
    await db.commit()
    return {"ok": True}


@router.get("/families/{family_id}/dashboard")
async def family_dashboard(
    family_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, membership = await get_family_membership(family_id, user, db)
    budgets = await get_family_budget_summaries(db, family_id)
    goals = await get_family_goal_summaries(db, family_id)

    sharing_ids = list(
        (
            await db.scalars(
                select(FamilyMember.user_id).where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.share_financial_summary.is_(True),
                )
            )
        ).all()
    )
    today = date.today()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = date(today.year + 1, 1, 1)
    else:
        period_end = date(today.year, today.month + 1, 1)
    totals = {"income": Decimal("0"), "expense": Decimal("0")}
    if sharing_ids:
        result = await db.execute(
            select(Transaction.kind, Transaction.amount, Transaction.currency).where(
                Transaction.user_id.in_(sharing_ids),
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date < period_end,
            )
        )
        for kind, amount, currency in result.all():
            totals[kind] += convert(Decimal(amount), currency, "USD")

    return {
        "family": family_summary(family, membership),
        "budgets": budgets,
        "goals": goals,
        "shared_summary": {
            "period_start": period_start,
            "currency": "USD",
            "income": totals["income"],
            "expenses": totals["expense"],
            "net": totals["income"] - totals["expense"],
            "sharing_member_count": len(sharing_ids),
            "is_sharing": membership.share_financial_summary,
        },
    }


@router.get("/families/{family_id}/notifications")
async def list_family_notifications(
    family_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_family_membership(family_id, user, db)
    result = await db.execute(
        select(FamilyNotification)
        .where(
            FamilyNotification.family_id == family_id,
            FamilyNotification.recipient_user_id == user.id,
        )
        .order_by(FamilyNotification.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id": item.id,
            "message": item.message,
            "created_at": item.created_at,
            "read": item.read_at is not None,
        }
        for item in result.scalars().all()
    ]


@router.post("/families/{family_id}/notifications/{notification_id}/read")
async def mark_family_notification_read(
    family_id: int,
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_family_membership(family_id, user, db)
    notification = await db.scalar(
        select(FamilyNotification).where(
            FamilyNotification.id == notification_id,
            FamilyNotification.family_id == family_id,
            FamilyNotification.recipient_user_id == user.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}
