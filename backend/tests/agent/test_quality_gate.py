import json
from unittest.mock import AsyncMock

import pytest

from app.agents.state import TaskType
from app.core.config import settings
from app.services.quality_gate import QualityGate


@pytest.mark.asyncio
async def test_quality_gate_uses_its_declared_model_and_one_llm_call():
    llm = AsyncMock()
    llm.chat.return_value = json.dumps(
        {
            "overall_score": 0.9,
            "metrics": {
                "task_completion": 0.9,
                "correctness": 0.9,
                "process_efficiency": 0.9,
                "expression": 0.9,
                "risk": 0.9,
            },
            "issues": [],
            "suggestions": [],
            "needs_replan": False,
            "needs_polish": False,
        }
    )

    result = await QualityGate(max_retries=1).evaluate(
        {"question": "结论是什么？", "answer": "结论已确认。", "task_type": TaskType.QA},
        llm,
    )

    assert result.passed is True
    llm.chat.assert_awaited_once()
    assert llm.chat.await_args.kwargs["model"] == settings.QUALITY_GATE_MODEL
