"""待办抽取微调、评估与推理共享的最小契约。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "meetingmind.todo-extraction.v1"
OUTPUT_FIELDS = (
    "content",
    "assignee",
    "deadline",
    "priority",
    "source_id",
    "source_type",
    "speaker",
    "timestamp",
    "uncertainties",
    "degradation_info",
)
SYSTEM_PROMPT = """你是会议待办抽取器。请从会议片段中抽取已经明确承诺、分配或要求执行的任务。
只输出 JSON 数组，不要 Markdown 和解释。没有待办时输出 []。不得把建议、问题、已完成事项或已取消事项当成待办，不得猜测负责人、期限和优先级。
每项字段必须是 content、assignee、deadline、priority、source_id、source_type、speaker、timestamp、uncertainties、degradation_info。
priority 只能是 high、medium、low、unknown；未知负责人或期限用空字符串，并在 uncertainties 写 assignee_missing 或 deadline_missing。"""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: str | Path, split: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            if split is None or item.get("split") == split:
                item["_line_number"] = line_number
                records.append(item)
    return records


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def render_user(record: dict[str, Any]) -> str:
    return (
        f"source_id: {record['sample_id']}\n"
        f"source_type: {record['source_type']}\n"
        f"会议片段：\n{record['transcript']}"
    )


def expected_json(record: dict[str, Any]) -> str:
    return compact_json(record["expected"])


def build_messages(
    record: dict[str, Any], few_shots: Sequence[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example in few_shots or ():
        messages.extend(
            [
                {"role": "user", "content": render_user(example)},
                {"role": "assistant", "content": expected_json(example)},
            ]
        )
    messages.append({"role": "user", "content": render_user(record)})
    return messages


def extract_json_array(text: str) -> Any:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end < start:
        raise ValueError("response does not contain a JSON array")
    return json.loads(re.sub(r",\s*([}\]])", r"\1", stripped[start : end + 1]))


def validate_todos(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("top-level output must be an array")
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")
        extra = set(item) - set(OUTPUT_FIELDS)
        missing = set(OUTPUT_FIELDS) - set(item)
        if extra or missing:
            raise ValueError(f"item {index} fields mismatch: extra={sorted(extra)}, missing={sorted(missing)}")
        if not isinstance(item["content"], str) or not item["content"].strip():
            raise ValueError(f"item {index} content must be a non-empty string")
        for field in ("assignee", "deadline", "source_id", "source_type"):
            if not isinstance(item[field], str):
                raise ValueError(f"item {index} {field} must be a string")
        if item["speaker"] is not None and not isinstance(item["speaker"], str):
            raise ValueError(f"item {index} speaker must be string or null")
        if item["timestamp"] is not None and not isinstance(item["timestamp"], (int, float)):
            raise ValueError(f"item {index} timestamp must be numeric or null")
        if item["priority"] not in {"high", "medium", "low", "unknown"}:
            raise ValueError(f"item {index} priority is invalid")
        for field in ("uncertainties", "degradation_info"):
            if not isinstance(item[field], list) or not all(isinstance(v, str) for v in item[field]):
                raise ValueError(f"item {index} {field} must be a string array")
        validated.append({field: item[field] for field in OUTPUT_FIELDS})
    return validated


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return float(ordered[position])


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return "|".join(sorted(normalize_text(item) for item in value))
    return re.sub(r"[\s，。！？、；：,.!?;:]", "", str(value)).lower()


def _counter(items: Iterable[Any]) -> Counter[str]:
    return Counter(normalize_text(item) for item in items if normalize_text(item))


def score_predictions(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """在冻结测试集上计算严格字段微平均指标，不做语义模型裁判。"""
    field_stats = {field: {"tp": 0, "pred": 0, "gold": 0} for field in OUTPUT_FIELDS}
    exact_samples = 0
    exact_items_tp = exact_items_pred = exact_items_gold = 0
    hallucinated = predicted_business_fields = 0

    for row in rows:
        predicted = row.get("predicted_validated", [])
        expected = row["expected"]
        if row.get("schema_valid") and predicted == expected:
            exact_samples += 1

        def item_key(item: dict[str, Any]) -> str:
            return "|".join(normalize_text(item.get(field)) for field in ("content", "assignee", "deadline"))

        pred_items = _counter(item_key(item) for item in predicted)
        gold_items = _counter(item_key(item) for item in expected)
        exact_items_tp += sum((pred_items & gold_items).values())
        exact_items_pred += sum(pred_items.values())
        exact_items_gold += sum(gold_items.values())

        for field in OUTPUT_FIELDS:
            pred_values = _counter(item.get(field) for item in predicted)
            gold_values = _counter(item.get(field) for item in expected)
            field_stats[field]["tp"] += sum((pred_values & gold_values).values())
            field_stats[field]["pred"] += sum(pred_values.values())
            field_stats[field]["gold"] += sum(gold_values.values())

        for item in predicted:
            for field in ("content", "assignee", "deadline"):
                value = normalize_text(item.get(field))
                if not value:
                    continue
                predicted_business_fields += 1
                gold_values = {normalize_text(gold.get(field)) for gold in expected}
                if value not in gold_values:
                    hallucinated += 1

    def prf(tp: int, pred: int, gold: int) -> dict[str, float]:
        precision = tp / pred if pred else (1.0 if gold == 0 else 0.0)
        recall = tp / gold if gold else (1.0 if pred == 0 else 0.0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"precision": precision, "recall": recall, "f1": f1}

    field_metrics = {
        field: {**counts, **prf(counts["tp"], counts["pred"], counts["gold"])}
        for field, counts in field_stats.items()
    }
    business = ["content", "assignee", "deadline"]
    business_tp = sum(field_stats[field]["tp"] for field in business)
    business_pred = sum(field_stats[field]["pred"] for field in business)
    business_gold = sum(field_stats[field]["gold"] for field in business)
    return {
        "sample_count": len(rows),
        "json_valid_rate": sum(bool(row.get("json_valid")) for row in rows) / len(rows) if rows else 0.0,
        "schema_valid_rate": sum(bool(row.get("schema_valid")) for row in rows) / len(rows) if rows else 0.0,
        "sample_exact_match": exact_samples / len(rows) if rows else 0.0,
        "item_exact": prf(exact_items_tp, exact_items_pred, exact_items_gold),
        "business_field_micro": prf(business_tp, business_pred, business_gold),
        "field_metrics": field_metrics,
        "hallucinated_business_field_rate": hallucinated / predicted_business_fields if predicted_business_fields else 0.0,
    }


def latency_summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean_ms": sum(values) / len(values) if values else 0.0,
        "p50_ms": median(values) if values else 0.0,
        "p95_ms": percentile(values, 0.95),
    }
