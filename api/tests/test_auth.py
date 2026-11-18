import time
from collections.abc import Iterator
from typing import Annotated, Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.auth import (
    AuthError,
    TokenClaims,
    decode_token,
    get_current_claims,
    require_permission,
)
from app.config import Settings, get_settings
from app.main import app as real_app

DOMAIN = "test.us.auth0.com"
AUDIENCE = "https://api.forkcheck"
ISSUER = f"https://{DOMAIN}/"

SETTINGS = Settings(auth0_domain=DOMAIN, auth0_audience=AUDIENCE)

# Two throwaway RSA key pairs: the "real" Auth0 key and an attacker's key.
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(key: rsa.RSAPrivateKey = KEY, algorithm: str = "RS256", **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "auth0|abc123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "permissions": ["review:allergens"],
    }
    claims.update(overrides)
    # A claim set to None means "leave this claim out".
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=algorithm)


def test_valid_token_returns_claims() -> None:
    claims = decode_token(make_token(), KEY.public_key(), SETTINGS)
    assert claims == TokenClaims(sub="auth0|abc123", permissions=["review:allergens"])


def test_token_without_permissions_gets_empty_list() -> None:
    claims = decode_token(make_token(permissions=None), KEY.public_key(), SETTINGS)
    assert claims.permissions == []


@pytest.mark.parametrize(
    "token",
    [
        make_token(key=OTHER_KEY),  # signed by the wrong key
        make_token(exp=int(time.time()) - 10),  # expired
        make_token(aud="https://some-other-api"),  # meant for a different API
        make_token(iss="https://evil.example.com/"),  # issued by someone else
        make_token(iss=f"https://{DOMAIN}"),  # missing trailing slash
        make_token(exp=None),  # no expiry
        make_token(sub=None),  # no subject
        "not-a-jwt",
    ],
)
def test_bad_tokens_are_rejected(token: str) -> None:
    with pytest.raises(AuthError):
        decode_token(token, KEY.public_key(), SETTINGS)


def test_hs256_token_is_rejected() -> None:
    # Classic attack: sign with HS256 using the public key as the secret.
    forged = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
        "secret-secret-secret-secret-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_token(forged, KEY.public_key(), SETTINGS)


def test_unconfigured_auth0_rejects_everything() -> None:
    with pytest.raises(AuthError):
        decode_token(make_token(), KEY.public_key(), Settings())


# --- the FastAPI dependency -------------------------------------------------

app = FastAPI()


@app.get("/whoami")
def whoami(claims: Annotated[TokenClaims, Depends(get_current_claims)]) -> TokenClaims:
    return claims


client = TestClient(app)


def test_missing_header_is_401() -> None:
    response = client.get("/whoami")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_401() -> None:
    response = client.get("/whoami", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


# --- require_permission, end to end ----------------------------------------


class FakeJWKSClient:
    """Stands in for Auth0's key server: always hands back our test public key."""

    def get_signing_key_from_jwt(self, token: str) -> rsa.RSAPublicKey:
        return KEY.public_key()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(auth, "get_jwks_client", lambda: FakeJWKSClient())
    for target in (app, real_app):
        target.dependency_overrides[get_settings] = lambda: SETTINGS
    yield
    for target in (app, real_app):
        target.dependency_overrides.clear()


@app.get("/reviews")
def reviews(
    claims: Annotated[TokenClaims, Depends(require_permission("review:allergens"))],
) -> TokenClaims:
    return claims


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("configured")
def test_permission_present_is_200() -> None:
    response = client.get("/reviews", headers=bearer(make_token()))
    assert response.status_code == 200


@pytest.mark.usefixtures("configured")
@pytest.mark.parametrize("permissions", [[], ["manage:catalog"], ["review:allergens:extra"]])
def test_permission_missing_is_403(permissions: list[str]) -> None:
    response = client.get("/reviews", headers=bearer(make_token(permissions=permissions)))
    assert response.status_code == 403


@pytest.mark.usefixtures("configured")
def test_no_token_on_protected_route_is_401_not_403() -> None:
    assert client.get("/reviews").status_code == 401


@pytest.mark.usefixtures("configured")
def test_me_returns_sub_for_valid_token() -> None:
    real_client = TestClient(real_app)
    response = real_client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 200
    assert response.json()["sub"] == "auth0|abc123"


@pytest.mark.usefixtures("configured")
def test_me_rejects_missing_token() -> None:
    assert TestClient(real_app).get("/me").status_code == 401
