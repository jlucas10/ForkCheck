from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from app.config import Settings, get_settings

# Only accept RS256. Pinning the algorithm stops "alg: none" and
# "switch RS256 to HS256" tricks, where an attacker picks a weaker algorithm.
ALGORITHMS = ["RS256"]

# Claims that must be present, or the token is rejected.
REQUIRED_CLAIMS = ["exp", "iss", "aud", "sub"]


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired or otherwise untrusted."""


class TokenClaims(BaseModel):
    """The parts of a verified token the API cares about."""

    sub: str  # Auth0 user id. Users are keyed by this, never by email.
    permissions: list[str] = Field(default_factory=list)


def decode_token(
    token: str, signing_key: jwt.PyJWK | RSAPublicKey, settings: Settings
) -> TokenClaims:
    """Verify a token's signature, issuer, audience and expiry; return its claims.

    Pure function: it does no network calls, so tests can pass in their own key.
    """
    # Fail closed: with no Auth0 config we cannot verify anything, so trust nothing.
    if not settings.auth0_domain or not settings.auth0_audience:
        raise AuthError("Auth0 is not configured")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=ALGORITHMS,
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer,
            options={"require": REQUIRED_CLAIMS},
        )
        return TokenClaims.model_validate(payload)
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthError("Invalid token") from exc


@lru_cache
def get_jwks_client() -> PyJWKClient:
    """One shared client that downloads and caches Auth0's public keys."""
    return PyJWKClient(get_settings().auth0_jwks_url)


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenClaims:
    """FastAPI dependency: turn an `Authorization: Bearer <token>` header into verified claims."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        # The token header names which key signed it (`kid`); fetch that public key.
        signing_key = get_jwks_client().get_signing_key_from_jwt(credentials.credentials)
        return decode_token(credentials.credentials, signing_key, settings)
    except (AuthError, jwt.PyJWTError) as exc:
        raise unauthorized from exc


def require_permission(permission: str) -> Callable[[TokenClaims], TokenClaims]:
    """Build a dependency that only lets through callers whose token has `permission`.

    Checks the permission string (e.g. "review:allergens"), never a role name.
    A caller who isn't logged in gets 401 (from get_current_claims); a logged-in
    caller without the permission gets 403.
    """

    def check(claims: Annotated[TokenClaims, Depends(get_current_claims)]) -> TokenClaims:
        if permission not in claims.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return claims

    return check
