import pytest

from app.config import Settings


def test_auth0_issuer_has_trailing_slash() -> None:
    settings = Settings(auth0_domain="example.us.auth0.com")
    assert settings.auth0_issuer == "https://example.us.auth0.com/"


def test_auth0_jwks_url() -> None:
    settings = Settings(auth0_domain="example.us.auth0.com")
    assert settings.auth0_jwks_url == "https://example.us.auth0.com/.well-known/jwks.json"


def test_auth0_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORKCHECK_AUTH0_DOMAIN", "env.us.auth0.com")
    monkeypatch.setenv("FORKCHECK_AUTH0_AUDIENCE", "https://api.forkcheck")
    settings = Settings()
    assert settings.auth0_domain == "env.us.auth0.com"
    assert settings.auth0_audience == "https://api.forkcheck"
