from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """App configuration, read from environment variables (and a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FORKCHECK_")

    app_env: str = "development"
    app_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
