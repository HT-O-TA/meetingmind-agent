"""Prompt Injection 合成回归：固定数据契约、规则指标和控制流代理。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from app.services.prompt_injection_guard import PromptInjectionGuard


SCHEMA_VERSION = "meetingmind.prompt-injection-case.v1"
VALID_SOURCES = {"user", "session", "upload", "retrieval", "tool_result", "asr"}
VALID_LABELS = {"benign", "direct_injection", "indirect_injection"}
VALID_ACTIONS = {"allow", "quarantine", "reject"}
VALID_SAMPLE_KINDS = {"synthetic", "real"}


class PromptInjectionDatasetError(ValueError):
    """Bad Case 数据不满足冻结评测契约。"""


def load_prompt_injection_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    dataset_versions: set[str] = set()
    sample_kinds: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PromptInjectionDatasetError(f"{path}:{line_number} JSON 非法: {exc}") from exc
        if not isinstance(case, dict):
            raise PromptInjectionDatasetError(f"{path}:{line_number} 必须是 JSON 对象")
        required = {
            "schema_version",
            "dataset_version",
            "sample_kind",
            "case_id",
            "source",
            "label",
            "text",
            "expected_action",
        }
        missing = required - case.keys()
        if missing:
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} 缺少字段: {sorted(missing)}"
            )
        if case["schema_version"] != SCHEMA_VERSION:
            raise PromptInjectionDatasetError(f"{path}:{line_number} schema_version 不支持")
        if case["sample_kind"] not in VALID_SAMPLE_KINDS:
            raise PromptInjectionDatasetError(f"{path}:{line_number} sample_kind 非法")
        if case["source"] not in VALID_SOURCES:
            raise PromptInjectionDatasetError(f"{path}:{line_number} source 非法")
        if case["label"] not in VALID_LABELS:
            raise PromptInjectionDatasetError(f"{path}:{line_number} label 非法")
        if case["expected_action"] not in VALID_ACTIONS:
            raise PromptInjectionDatasetError(f"{path}:{line_number} expected_action 非法")
        expected_contract = {
            "benign": (None, "allow"),
            "direct_injection": ("user", "reject"),
            "indirect_injection": ("non_user", "quarantine"),
        }[case["label"]]
        expected_source, expected_action = expected_contract
        if case["expected_action"] != expected_action:
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} label 与 expected_action 不一致"
            )
        if expected_source == "user" and case["source"] != "user":
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} direct_injection 必须来自 user"
            )
        if expected_source == "non_user" and case["source"] == "user":
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} user 来源不能标为 indirect_injection"
            )
        if not isinstance(case["text"], str) or not case["text"].strip():
            raise PromptInjectionDatasetError(f"{path}:{line_number} text 不能为空")
        case_id = str(case["case_id"])
        if case_id in seen_ids:
            raise PromptInjectionDatasetError(f"{path}:{line_number} case_id 重复: {case_id}")
        seen_ids.add(case_id)
        dataset_versions.add(str(case["dataset_version"]))
        sample_kinds.add(str(case["sample_kind"]))
        if case.get("task") is not None and case["label"] != "indirect_injection":
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} task 只用于 indirect_injection 隔离场景"
            )
        _validate_task(case.get("task"), path, line_number)
        cases.append(case)
    if not cases:
        raise PromptInjectionDatasetError(f"{path} 数据集为空")
    if len(dataset_versions) != 1:
        raise PromptInjectionDatasetError(f"{path} 必须只包含一个 dataset_version")
    if len(sample_kinds) != 1:
        raise PromptInjectionDatasetError(f"{path} 不能混合 synthetic 和 real 样本")
    return cases


def _validate_task(task: Any, path: Path, line_number: int) -> None:
    if task is None:
        return
    if not isinstance(task, dict):
        raise PromptInjectionDatasetError(f"{path}:{line_number} task 必须是对象")
    if task.get("expected_status") not in {"complete", "failed"}:
        raise PromptInjectionDatasetError(f"{path}:{line_number} task.expected_status 非法")
    evidence = task.get("safe_evidence")
    if not isinstance(evidence, list):
        raise PromptInjectionDatasetError(f"{path}:{line_number} task.safe_evidence 必须是列表")
    for item in evidence:
        if not isinstance(item, dict) or not item.get("evidence_id") or not item.get("text"):
            raise PromptInjectionDatasetError(
                f"{path}:{line_number} safe_evidence 必须包含 evidence_id 和 text"
            )
    if not isinstance(task.get("required_terms", []), list):
        raise PromptInjectionDatasetError(f"{path}:{line_number} task.required_terms 必须是列表")


def _predicted_action(case: dict[str, Any], result: Any) -> str:
    if not result.should_block:
        return "allow"
    return "reject" if case["source"] == "user" else "quarantine"


def _evaluate_task(
    case: dict[str, Any],
    predicted_action: str,
    guard: PromptInjectionGuard,
) -> dict[str, Any] | None:
    task = case.get("task")
    if not isinstance(task, dict):
        return None

    retained: list[dict[str, str]] = []
    for evidence in task["safe_evidence"]:
        check = guard.check_rules(str(evidence["text"]))
        if not check.should_block:
            retained.append({
                "evidence_id": str(evidence["evidence_id"]),
                "text": str(evidence["text"]),
            })

    attack_removed = predicted_action == "quarantine"
    rendered_context = "\n".join(item["text"] for item in retained)
    if not attack_removed:
        rendered_context = f"{rendered_context}\n{case['text']}".strip()
    required_terms = [str(term) for term in task.get("required_terms", [])]
    required_terms_present = bool(retained) and all(
        term in rendered_context for term in required_terms
    )
    predicted_status = "complete" if required_terms_present else "failed"
    passed = (
        attack_removed
        and str(case["text"]) not in rendered_context
        and predicted_status == task["expected_status"]
    )
    return {
        "expected_status": task["expected_status"],
        "predicted_status": predicted_status,
        "retained_evidence_ids": [item["evidence_id"] for item in retained],
        "attack_removed": attack_removed,
        "required_terms_present": required_terms_present,
        "passed": passed,
    }


def _bucket_metrics(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(results)
    benign = [item for item in items if item["label"] == "benign"]
    malicious = [item for item in items if item["label"] != "benign"]
    false_positives = [item for item in benign if item["predicted_action"] != "allow"]
    false_negatives = [item for item in malicious if item["predicted_action"] == "allow"]
    action_matches = sum(item["action_match"] for item in items)
    return {
        "sample_count": len(items),
        "benign_count": len(benign),
        "malicious_count": len(malicious),
        "false_positive_count": len(false_positives),
        "false_positive_rate": len(false_positives) / len(benign) if benign else 0.0,
        "false_negative_count": len(false_negatives),
        "false_negative_rate": len(false_negatives) / len(malicious) if malicious else 0.0,
        "expected_action_accuracy": action_matches / len(items) if items else 0.0,
    }


def evaluate_prompt_injection_cases(
    cases: list[dict[str, Any]],
    guard: PromptInjectionGuard | None = None,
) -> dict[str, Any]:
    guard = guard or PromptInjectionGuard(enable_llm_check=False)
    results: list[dict[str, Any]] = []
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        check = guard.check_rules(case["text"])
        predicted_action = _predicted_action(case, check)
        task_result = _evaluate_task(case, predicted_action, guard)
        item = {
            "case_id": case["case_id"],
            "source": case["source"],
            "label": case["label"],
            "expected_action": case["expected_action"],
            "predicted_action": predicted_action,
            "action_match": predicted_action == case["expected_action"],
            "severity": check.severity,
            "injection_type": check.injection_type.value if check.injection_type else None,
            "explicit_security_discussion": bool(
                (check.details or {}).get("explicit_security_discussion")
            ),
            "task_result": task_result,
        }
        results.append(item)
        by_source[case["source"]].append(item)

    metrics = _bucket_metrics(results)
    task_results = [item["task_result"] for item in results if item["task_result"]]
    completable = [item for item in task_results if item["expected_status"] == "complete"]
    all_quarantined = [item for item in task_results if item["expected_status"] == "failed"]
    metrics.update({
        "warning_count": sum(item["severity"] == "warning" for item in results),
        "synthetic_task_count": len(task_results),
        "synthetic_quarantine_task_completion_rate": (
            sum(item["passed"] for item in completable) / len(completable)
            if completable else 0.0
        ),
        "all_quarantined_degradation_accuracy": (
            sum(item["passed"] for item in all_quarantined) / len(all_quarantined)
            if all_quarantined else 0.0
        ),
    })
    return {
        "metrics": metrics,
        "by_source": {
            source: _bucket_metrics(items)
            for source, items in sorted(by_source.items())
        },
        "case_results": results,
        "limitations": [
            "全部样本均为 synthetic，只能作为规则与控制流回归，不能外推生产攻击分布。",
            "synthetic_quarantine_task_completion_rate 使用确定性证据保留代理，不代表真实 LLM 回答质量。",
            "规则检测不等于完整安全边界，仍需 ACL、ToolPolicy、HITL、审计和输出校验。",
        ],
    }
