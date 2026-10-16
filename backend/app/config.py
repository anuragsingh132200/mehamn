from typing import Literal
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Direct connections support the app's PostgreSQL startup timeouts.
    database_url: str = Field(
        "postgresql+psycopg://mira:mira@localhost:5432/mira",
        validation_alias=AliasChoices("DATABASE_URL_UNPOOLED", "DATABASE_URL", "database_url"),
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg(cls, value: str) -> str:
        # Hosted providers supply plain Postgres URLs; this app uses psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    llm_mode: Literal["openai"] = "openai"
    recent_message_window: int = Field(12, ge=2, le=30)
    context_message_chars: int = Field(2000, ge=200, le=4000)
    context_tool_window: int = Field(12, ge=1, le=20)
    max_model_calls: int = Field(4, ge=2, le=6)
    max_planning_rounds: int = Field(2, ge=1, le=2)
    max_agent_tools: int = Field(12, ge=1, le=16)
    model_timeout_seconds: float = Field(15, ge=1, le=60)
    agent_timeout_seconds: float = Field(55, ge=5, le=120)
    model_max_output_tokens: int = Field(3000, ge=500, le=6000)
    admin_token: str = ""
    cors_origin: str = "http://localhost:3000"
    quote_minutes: int = 15
    hold_minutes: int = 10
    rate_limit_per_minute: int = 30

settings = Settings()
