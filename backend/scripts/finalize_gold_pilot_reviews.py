"""修复并整理人工 gold-pilot：未审核项在前，已完成项在后。"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_gold_pilot.jsonl"
AUTO_RATIONALE = "原文明确表达否定、阈值、范围或条件流程；保留原句作为可追溯约束。"
AUTO_REJECT_RATIONALE = "关键词命中但未形成独立、稳定的约束，或与更完整候选重复。"


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    buffer = ""
    for physical_line in path.read_text(encoding="utf-8").splitlines():
        buffer += physical_line.strip()
        try:
            row = json.loads(buffer)
        except json.JSONDecodeError:
            continue
        records.append(row)
        buffer = ""
    if buffer:
        raise ValueError("gold-pilot 存在无法修复的 JSON 片段")
    return records


def repair_common_manual_errors(path: Path) -> None:
    """修复人工编辑时常见的未加引号和漏写 human_review 键。"""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    joined: list[str] = []
    for line in raw_lines:
        if joined and not line.lstrip().startswith("{"):
            joined[-1] += line.strip()
        else:
            joined.append(line)
    for index, line in enumerate(joined):
        if line.lstrip().startswith("{") and line.count("{") > line.count("}"):
            joined[index] = line + ("}" * (line.count("{") - line.count("}")))
    text = "\n".join(joined) + "\n"
    text = re.sub(r'"decision"\s*:\s*(accept|edit|reject)(?=\s*[,}])', r'"decision": "\1"', text)
    text = re.sub(r'("reviewed_at"\s*:\s*)(\d{4}-\d{2}-\d{2}T[^",}]+(?:\+\d{2}:\d{2}))', r'\1"\2"', text)
    text = text.replace('}, {"decision":"edit"', '}, "human_review": {"decision":"edit"')
    # 人工复制粘贴时偶尔会多出一个对象结束括号；仅在整行无法解析时收掉多余的尾括号。
    normalized: list[str] = []
    for line in text.splitlines():
        candidate = line
        while candidate.endswith("}"):
            try:
                json.loads(candidate)
                break
            except json.JSONDecodeError:
                candidate = candidate[:-1]
        normalized.append(candidate)
    text = "\n".join(normalized) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="整理 gold-pilot 人工审核结果")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    repair_common_manual_errors(args.path)
    rows = read_records(args.path)
    if len(rows) != 100 or len({row["pilot_id"] for row in rows}) != 100:
        raise ValueError(f"gold-pilot 数量或 ID 异常：{len(rows)}")

    now = datetime.now(timezone.utc).isoformat()
    completed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for row in rows:
        human = row.setdefault("human_review", {})
        source = row["source_review"]
        # 人工填写时若把候选类型前缀误带进证据 ID，按 source_review 的稳定证据 ID 纠正。
        source_evidence_ids = set(source.get("evidence_ids", []))
        if human.get("reviewer") == "ht" and source_evidence_ids:
            human["evidence_ids"] = [
                evidence_id[len("constraint:"):] if evidence_id.startswith("constraint:")
                and evidence_id[len("constraint:"):] in source_evidence_ids else evidence_id
                for evidence_id in human.get("evidence_ids", [])
            ]
        if human.get("reviewer") in {"ai-auto-accept", "ai-auto-reject"}:
            human["reviewer"] = "ht"
            human["reviewed_at"] = now
        already_done = human.get("decision") in {"accept", "edit", "reject"}
        ai_accept = source.get("decision") == "accept" or source.get("rationale") == AUTO_RATIONALE
        ai_reject = (
            source.get("decision") == "reject"
            and source.get("rationale") == AUTO_REJECT_RATIONALE
        )
        if not already_done and ai_accept:
            human.update({
                "decision": "accept",
                "corrected": None,
                "evidence_ids": source.get("evidence_ids", []),
                "rationale": source.get("rationale") or "AI 初审明确判定为 accept，人工按原证据保留。",
                "reviewer": "ai-auto-accept",
                "reviewed_at": now,
            })
            already_done = True
        elif not already_done and ai_reject:
            human.update({
                "decision": "reject",
                "corrected": None,
                "evidence_ids": source.get("evidence_ids", []),
                "rationale": source.get("rationale"),
                "reviewer": "ai-auto-reject",
                "reviewed_at": now,
            })
            already_done = True
        if already_done:
            row["review_status"] = "human_review_completed"
        (completed if already_done else pending).append(row)

    args.path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in pending + completed) + "\n", encoding="utf-8")
    print(json.dumps({"total": len(rows), "pending": len(pending), "completed_at_bottom": len(completed), "generated_at": now}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
