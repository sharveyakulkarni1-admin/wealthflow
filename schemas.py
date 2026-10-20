from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, computed_field, field_validator, model_validator


CURRENCIES = {"USD", "EUR", "GBP", "INR"}
KINDS = {"income", "expense"}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    base_currency: str = "USD"

    @field_validator("base_currency")
    @classmethod
    def currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    base_currency: str
    theme: str = "system"
    date_format: str = "iso"
    created_at: datetime | None = None


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("full_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class PreferencesUpdate(BaseModel):
    theme: Literal["dark", "light", "system"]
    date_format: Literal["iso", "us", "eu"]
    base_currency: str

    @field_validator("base_currency")
    @classmethod
    def supported_currency(cls, value: str) -> str:
        value = value.upper().strip()
        if value not in CURRENCIES:
            raise ValueError("Unsupported display currency")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=72)
    confirm_password: str = Field(min_length=12, max_length=72)

    @field_validator("new_password", "confirm_password")
    @classmethod
    def bcrypt_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def new_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password confirmation does not match")
        if self.new_password == self.current_password:
            raise ValueError("Choose a new password different from the current password")
        return self


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    category: Literal["Account", "Transactions", "Import/Export", "Security", "General"]
    message: str = Field(min_length=10, max_length=5000)
    contact_email: EmailStr | None = None

    @field_validator("subject", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class SupportTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subject: str
    category: str
    message: str
    contact_email: str | None
    status: str
    created_at: datetime


class AiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def strip_nonblank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class AiChatResponse(BaseModel):
    conversation_id: UUID
    message: str
    data_used: list[str]


class AiNewChatResponse(BaseModel):
    conversation_id: UUID


class TransactionCreate(BaseModel):
    transaction_date: date
    kind: str
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    category: str = Field(min_length=1, max_length=80)
    merchant: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        value = value.lower()
        if value not in KINDS:
            raise ValueError("kind must be income or expense")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class TransactionOut(BaseModel):
    id: int
    transaction_date: date
    kind: str
    amount: Decimal
    currency: str
    amount_base: Decimal
    category: str
    merchant: str
    note: str
    tags: list[str]


class TransactionImportMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_date: str | None = None
    kind: str | None = None
    amount: str | None = None
    currency: str | None = None
    category: str | None = None
    merchant: str | None = None
    note: str | None = None
    tags: str | None = None


class BudgetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    amount: Decimal
    month: int
    year: int


class RecurringCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    category: str = Field(min_length=1, max_length=80)
    frequency: str
    next_due: date
    active: bool = True

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        value = value.lower()
        if value not in KINDS:
            raise ValueError("kind must be income or expense")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        value = value.lower()
        if value not in {"weekly", "monthly", "yearly"}:
            raise ValueError("frequency must be weekly, monthly, or yearly")
        return value


class RecurringOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    amount: Decimal
    currency: str
    category: str
    frequency: str
    next_due: date
    active: bool

class SavingsGoalBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "USD"
    deadline: date | None = None
    description: str = Field(default="", max_length=500)

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class SavingsGoalCreate(SavingsGoalBase):
    saved_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)

    @model_validator(mode="after")
    def saved_amount_within_target(self):
        if self.saved_amount > self.target_amount:
            raise ValueError("Saved amount cannot exceed target amount")
        return self


class SavingsGoalUpdate(SavingsGoalBase):
    pass


class SavingsGoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    currency: str
    deadline: date | None
    description: str = ""

    @computed_field
    @property
    def remaining_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.target_amount - self.saved_amount)

    @computed_field
    @property
    def progress_percentage(self) -> Decimal:
        progress = self.saved_amount / self.target_amount * Decimal("100")
        return min(Decimal("100.0"), progress.quantize(Decimal("0.1")))

    @computed_field
    @property
    def status(self) -> str:
        if self.saved_amount >= self.target_amount:
            return "completed"
        if self.deadline is not None and self.deadline < date.today():
            return "overdue"
        return "active"


class SavingsGoalContribution(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


NET_WORTH_CATEGORIES = {
    "asset": {"cash", "savings", "investment", "property", "vehicle", "other"},
    "liability": {"loan", "debt", "mortgage", "credit_card", "other"},
}


class NetWorthItemInput(BaseModel):
    kind: Literal["asset", "liability"]
    name: str = Field(min_length=1, max_length=120)
    category: str
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "USD"

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip().lower()
        kind = info.data.get("kind")
        if kind not in NET_WORTH_CATEGORIES or value not in NET_WORTH_CATEGORIES[kind]:
            raise ValueError("Choose a category valid for this entry type")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value


class NetWorthItemOut(BaseModel):
    id: int
    kind: Literal["asset", "liability"]
    name: str
    category: str
    amount: Decimal
    currency: str
    amount_base: Decimal
    updated_at: datetime | None = None


class NetWorthSnapshotOut(BaseModel):
    snapshot_date: date
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal


class NetWorthSummaryOut(BaseModel):
    base_currency: str
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    assets: list[NetWorthItemOut]
    liabilities: list[NetWorthItemOut]
    history: list[NetWorthSnapshotOut]
