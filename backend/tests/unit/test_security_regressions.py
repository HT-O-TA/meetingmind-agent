import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.user import UserCreate
from app.services.llm_service import LLMService


def test_production_requires_non_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="meetingmind-secret-key-change-in-production",
        )


def test_production_accepts_custom_secret_key():
    secret = "custom-production-secret-at-least-32-characters"
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY=secret,
        CORS_ORIGINS='["https://meetingmind.example"]',
    )

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
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="safe-production-secret-at-least-32-characters",
            CORS_ORIGINS='["http://localhost:5173"]',
        )


def test_environment_secret_provider_is_injectable_without_logging_values(monkeypatch):
    from app.core.secret_provider import EnvironmentSecretProvider

    monkeypatch.setenv("MEETINGMIND_TEST_TOKEN", "  private-value  ")
    provider = EnvironmentSecretProvider()

    assert provider.get("MEETINGMIND_TEST_TOKEN") == "private-value"
    with pytest.raises(RuntimeError, match="MISSING_TOKEN"):
        provider.get("MISSING_TOKEN", required=True)


def test_bcrypt_password_limit_rejects_multibyte_overflow():
    with pytest.raises(ValidationError, match="72"):
        UserCreate(username="tester", email="tester@example.com", password="密" * 25)


def test_llm_service_can_initialize_without_key_for_retrieval_only(monkeypatch):
    from app.services import llm_service as module

    monkeypatch.setattr(module.settings, "LLM_API_KEY", "")
    service = LLMService()

    with pytest.raises(ValueError, match="model generation"):
        service._get_client()
