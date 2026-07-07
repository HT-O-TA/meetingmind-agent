import pytest
from pydantic import ValidationError

from app.agents.tools.builtin import execute_builtin_tool
from app.core.config import Settings


def test_calculator_rejects_non_math_expressions():
    result = execute_builtin_tool(
        "calculator",
        {"expression": "__import__('os').system('echo unsafe')"},
    )

    assert result == "计算错误"


def test_calculator_accepts_basic_arithmetic():
    result = execute_builtin_tool("calculator", {"expression": "2 + 3 * 4"})

    assert result == 14


def test_production_requires_non_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="meetingmind-secret-key-change-in-production",
        )


def test_production_accepts_custom_secret_key():
    settings = Settings(APP_ENV="production", SECRET_KEY="custom-production-secret")

    assert settings.SECRET_KEY == "custom-production-secret"
