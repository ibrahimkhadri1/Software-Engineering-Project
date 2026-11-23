from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    frontend_origin: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://autograder:autograder@127.0.0.1:5432/autograder"
    log_level: str = "INFO"
    grade_concurrency: int = 5
    data_ttl_hours: int = 48


@lru_cache
def get_settings() -> Settings:
    return Settings()
