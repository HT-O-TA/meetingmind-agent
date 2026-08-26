import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_non_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="meetingmind-secret-key-change-in-production",
        )


def test_production_accepts_custom_secret_key():
    secret = "custom-production-secret-at-least-32-characters"
    settings = Settings(APP_ENV="production", SECRET_KEY=secret)

    assert settings.SECRET_KEY == secret


def test_production_rejects_short_or_example_secrets_and_wildcard_cors():
    for secret in (
        "short-secret",
        "your-secret-key-here-change-in-production",
        "meetingmind-dev-only-secret-change-before-production",
    ):
        with pytest.raises(ValidationError):
            Settings(APP_ENV="production", SECRET_KEY=secret)

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="safe-production-secret-at-least-32-characters",
            CORS_ORIGINS='["*"]',
        )
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="safe-production-secret-at-least-32-characters",
            DEBUG=True,
        )


def test_environment_secret_provider_is_injectable_without_logging_values(monkeypatch):
    from app.core.secret_provider import EnvironmentSecretProvider

    monkeypatch.setenv("MEETINGMIND_TEST_TOKEN", "  private-value  ")
    provider = EnvironmentSecretProvider()

    assert provider.get("MEETINGMIND_TEST_TOKEN") == "private-value"
    with pytest.raises(RuntimeError, match="MISSING_TOKEN"):
        provider.get("MISSING_TOKEN", required=True)
