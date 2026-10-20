from collections.abc import AsyncGenerator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./wealth.db"
    jwt_secret: str = "change-this-to-a-long-random-secret"
    jwt_expire_minutes: int = 1440
    cookie_secure: bool = False
    admin_password: str = ""
    ai_api_key: str = Field(default="", validation_alias="WEALTHFLOW_AI_API_KEY")
    ai_model: str = Field(default="gemini-4-argon", validation_alias="WEALTHFLOW_AI_MODEL")
    ai_timeout_seconds: int = Field(default=30, ge=5, le=90, validation_alias="WEALTHFLOW_AI_TIMEOUT_SECONDS")
    ai_history_messages: int = Field(default=8, ge=2, le=20, validation_alias="WEALTHFLOW_AI_HISTORY_MESSAGES")
    ai_requests_per_hour: int = Field(default=30, ge=1, le=120, validation_alias="WEALTHFLOW_AI_REQUESTS_PER_HOUR")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def _migrate_savings_goals(connection: Connection) -> None:
    if not inspect(connection).has_table("savings_goals"):
        return

    columns = {column["name"] for column in inspect(connection).get_columns("savings_goals")}
    if "description" not in columns:
        connection.execute(
            text("ALTER TABLE savings_goals ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        )


def _migrate_user_settings(connection: Connection) -> None:
    if not inspect(connection).has_table("users"):
        return

    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    additions = {
        "theme": "VARCHAR(16) NOT NULL DEFAULT 'system'",
        "date_format": "VARCHAR(8) NOT NULL DEFAULT 'iso'",
        "session_version": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {column} {definition}"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from models import Base as ModelsBase
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
        await conn.run_sync(_migrate_savings_goals)
        await conn.run_sync(_migrate_user_settings)
