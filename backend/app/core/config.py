from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    frontend_origin: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://autograder:autograder@127.0.0.1:5432/autograder"
    log_level: str = "INFO"
    grade_concurrency: int = 5
    data_ttl_hours: int = 48
    auth0_domain: str = "dev-g10vglwx2yb2sdn2.us.auth0.com"
    auth0_audience: str = "https://canvas-autograder-api"
    ai_mode: Literal["fake", "bedrock"] = "fake"
    aws_region: str = "us-west-2"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
