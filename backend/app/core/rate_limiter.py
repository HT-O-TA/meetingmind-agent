"""关键 API 的 Redis 固定窗口限流门禁。"""

from hashlib import sha256
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, Response

from app.core import cache_init
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User


def _identity_digest(identity: str) -> str:
    return sha256(identity.encode("utf-8")).hexdigest()[:24]


def _client_ip(request: Request) -> str:
    # 不直接信任可伪造的 X-Forwarded-For；反向代理应先规范化 client.host。
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    *,
    response: Response,
    bucket: str,
    identity: str,
    limit: int,
    window: int,
) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return

    key = f"rate_limit:{bucket}:{_identity_digest(identity)}"
    try:
        allowed, count, configured_limit, retry_after = await cache_init.rate_limit(
            key,
            limit=limit,
            window=window,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="限流服务暂时不可用，请稍后重试",
        ) from exc

    remaining = max(0, configured_limit - count)
    response.headers["X-RateLimit-Limit"] = str(configured_limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(retry_after)
    if not allowed:
        headers = {
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(configured_limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(retry_after),
        }
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后重试",
            headers=headers,
        )


async def enforce_anonymous_rate_limit(
    *,
    request: Request,
    response: Response,
    bucket: str,
    limit: int,
    window: int,
    subject: Optional[str] = None,
) -> None:
    await enforce_rate_limit(
        response=response,
        bucket=f"{bucket}:ip",
        identity=_client_ip(request),
        limit=limit,
        window=window,
    )
    if subject:
        await enforce_rate_limit(
            response=response,
            bucket=f"{bucket}:subject",
            identity=subject.strip().casefold(),
            limit=limit,
            window=window,
        )


def user_rate_limit(
    bucket: str,
    limit: int,
    window: int,
) -> Callable:
    async def dependency(
        request: Request,
        response: Response,
        current_user: User = Depends(get_current_user),
    ) -> None:
        await enforce_rate_limit(
            response=response,
            bucket=bucket,
            identity=f"user:{current_user.id}",
            limit=limit,
            window=window,
        )

    return dependency
