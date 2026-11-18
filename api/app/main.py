from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.auth import TokenClaims, get_current_claims
from app.config import get_settings


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


app = FastAPI(title="ForkCheck API")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app_version, env=settings.app_env)


@app.get("/me", response_model=TokenClaims)
def me(claims: Annotated[TokenClaims, Depends(get_current_claims)]) -> TokenClaims:
    """Who am I? Requires a valid token; used to prove sign-in works end to end."""
    return claims
