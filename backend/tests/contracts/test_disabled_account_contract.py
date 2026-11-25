from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_disabled_account_rejects_previously_issued_token():
    user = SimpleNamespace(id=42, is_active=True)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: user)
    authorization = "Bearer " + create_access_token({"sub": str(user.id)})
    assert await get_current_user(authorization, db) is user
    user.is_active = False
    with pytest.raises(AppException) as error:
        await get_current_user(authorization, db)
    assert error.value.code == 401
