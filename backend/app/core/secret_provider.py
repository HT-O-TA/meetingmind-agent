"""密钥读取边界；默认只从进程环境读取，不记录密钥内容。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol


class SecretProvider(Protocol):
    def get(self, name: str, *, required: bool = False) -> Optional[str]:
        """返回密钥；required=True 且缺失时必须失败。"""


@dataclass(frozen=True)
class EnvironmentSecretProvider:
    prefix: str = ""

    def get(self, name: str, *, required: bool = False) -> Optional[str]:
        value = os.environ.get(f"{self.prefix}{name}")
        if value is not None:
            value = value.strip()
        if required and not value:
            raise RuntimeError(f"required secret is missing: {name}")
        return value or None


_provider: SecretProvider = EnvironmentSecretProvider()


def get_secret_provider() -> SecretProvider:
    return _provider


def set_secret_provider(provider: SecretProvider) -> None:
    """允许部署适配 Vault/KMS，也便于测试注入；调用方不得记录返回值。"""
    global _provider
    _provider = provider
