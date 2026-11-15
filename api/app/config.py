from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment variables (and a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FORKCHECK_")

    app_env: str = "development"
    app_version: str = "0.1.0"

    # Auth0 (empty until the tenant exists; JWT validation will refuse to run if unset).
    auth0_domain: str = ""  # e.g. "your-tenant.us.auth0.com" (no https://)
    auth0_audience: str = ""  # the API identifier registered in Auth0

    @property
    def auth0_issuer(self) -> str:
        """The `iss` claim Auth0 puts in tokens. The trailing slash is required."""
        return f"https://{self.auth0_domain}/"

    @property
    def auth0_jwks_url(self) -> str:
        """Where Auth0 publishes the public keys used to verify token signatures."""
        return f"https://{self.auth0_domain}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
