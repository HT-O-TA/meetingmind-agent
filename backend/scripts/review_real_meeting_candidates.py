"""独立复核 MeetingMind 真实会议候选，输出 AI-reviewed silver（不是人工 gold）。

复核依据：
- VCSUM 问答的答案采用上游 long_test/short_test 标注；
- 问答引用由上游 highlights 或完整 topic context 重建，避免候选截断漏引；
- VCSUM 待办不把讨论、历史陈述或说话人编号推断为责任人；
- AliMeeting 待办/约束仅保留明确、可追溯的高置信度项目。

该脚本不会修改候选文件，也不会把任何记录提升为 gold。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "backend" / "evaluation" / "datasets"
DEFAULT_DATA_ROOT = REPO_ROOT / "data"

ALI_TODO_EDITS: dict[str, list[str]] = {
    "todo:ali:R8001_M8004:0136": ["为盲盒赠品添加品牌 Logo。", "与供应商洽谈赠品方案并控制成本。"],
    "todo:ali:R8001_M8004:0141": ["列出拟加入盲盒的产品清单。", "联系多家供应商获取报价并比较方案。", "在预算内控制产品成本。"],
    "todo:ali:R8001_M8004:0149": ["整理候选供应商清单并逐一联系。", "为供应商沟通安排专人。"],
    "todo:ali:R8001_M8004:0167": ["安排人员落实供应商和产品方案。", "向市场、销售部门确认产品主打颜色和主推意向。"],
    "todo:ali:R8001_M8004:0191": ["联系多家赠品厂家并比较方案。"],
    "todo:ali:R8003_M8001:0044": ["送礼前提前联系老师。"],
    "todo:ali:R8007_M8010:0392": ["现场考察房屋前先调查清楚实际情况。"],
    "todo:ali:R8007_M8011:0060": ["增加后台监控，用于识别虚假客服。"],
    "todo:ali:R8008_M8013:0039": ["在招聘网站发布岗位信息和相关要求。"],
    "todo:ali:R8008_M8013:0072": ["为拟招聘的各类经理明确岗位职责。"],
}

CONFIRMED_CONSTRAINTS = {
    "constraint:vcsum:4:seg:14:utt:0",
    "constraint:vcsum:23:seg:9:utt:8",
    "constraint:vcsum:31:seg:6:utt:5",
    "constraint:vcsum:31:seg:23:utt:2",
    "constraint:vcsum:38:seg:3:utt:2",
    "constraint:vcsum:38:seg:9:utt:3",
    "constraint:vcsum:38:seg:24:utt:6",
    "constraint:vcsum:38:seg:38:utt:4",
    "constraint:vcsum:38:seg:48:utt:17",
    "constraint:vcsum:38:seg:69:utt:4",
    "constraint:vcsum:86:seg:0:utt:2",
    "constraint:vcsum:108:seg:24:utt:4",
    "constraint:vcsum:125:seg:51:utt:0",
    "constraint:vcsum:146:seg:2:utt:1",
    "constraint:vcsum:146:seg:2:utt:3",
    "constraint:vcsum:150:seg:34:utt:2",
    "constraint:vcsum:150:seg:36:utt:2",
    "constraint:vcsum:150:seg:40:utt:2",
    "constraint:vcsum:150:seg:42:utt:2",
    "constraint:vcsum:150:seg:47:utt:5",
    "constraint:vcsum:165:seg:0:utt:4",
    "constraint:vcsum:165:seg:2:utt:7",
    "constraint:vcsum:165:seg:6:utt:2",
    "constraint:vcsum:165:seg:9:utt:8",
    "constraint:vcsum:165:seg:9:utt:12",
    "constraint:vcsum:165:seg:10:utt:0",
    "constraint:vcsum:172:seg:17:utt:3",
    "constraint:vcsum:172:seg:79:utt:2",
    "constraint:vcsum:176:seg:36:utt:1",
    "constraint:vcsum:185:seg:11:utt:11",
    "constraint:vcsum:185:seg:17:utt:2",
    "constraint:vcsum:185:seg:31:utt:3",
    "constraint:vcsum:201:seg:17:utt:0",
    "constraint:vcsum:201:seg:47:utt:2",
    "constraint:vcsum:201:seg:50:utt:0",
    "constraint:vcsum:208:seg:53:utt:0",
    "constraint:vcsum:208:seg:53:utt:1",
    "constraint:vcsum:208:seg:54:utt:6",
    "constraint:vcsum:208:seg:55:utt:0",
    "constraint:vcsum:208:seg:55:utt:3",
    "constraint:ali:R8001_M8004:0098",
    "constraint:ali:R8001_M8004:0137",
    "constraint:ali:R8001_M8004:0194",
    "constraint:ali:R8001_M8004:0249",
    "constraint:ali:R8001_M8004:0386",
    "constraint:ali:R8001_M8004:0440",
    "constraint:ali:R8001_M8004:0452",
    "constraint:ali:R8003_M8001:0017",
    "constraint:ali:R8003_M8001:0110",
    "constraint:ali:R8003_M8001:0220",
    "constraint:ali:R8003_M8001:0236",
    "constraint:ali:R8003_M8001:0388",
    "constraint:ali:R8007_M8010:0137",
    "constraint:ali:R8007_M8010:0397",
    "constraint:ali:R8007_M8010:0430",
    "constraint:ali:R8007_M8010:0444",
    "constraint:ali:R8007_M8010:0469",
    "constraint:ali:R8007_M8010:0485",
    "constraint:ali:R8007_M8010:0493",
    "constraint:ali:R8007_M8011:0131",
    "constraint:ali:R8007_M8011:0292",
    "constraint:ali:R8007_M8011:0500",
    "constraint:ali:R8007_M8011:0606",
    "constraint:ali:R8007_M8011:0615",
    "constraint:ali:R8007_M8011:0635",
    "constraint:ali:R8008_M8013:0233",
    "constraint:ali:R8008_M8013:0270",
    "constraint:ali:R8008_M8013:0350",
    "constraint:ali:R8008_M8013:0469",
    "constraint:ali:R8008_M8013:0474",
    "constraint:ali:R8008_M8013:0683",
    "constraint:ali:R8008_M8013:0708",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stable_jsonl_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    normalized = text.rstrip("\n") + "\n" if text else ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def classify_constraint(text: str) -> str:
    if any(word in text for word in ("不要", "不得", "不能", "不应", "除非", "排除", "取消")):
        return "negative"
    if any(word in text for word in ("不超过", "低于", "高于", "至少", "预算", "上限", "以内", "以上", "以下")):
        return "threshold"
    return "overwrite_or_scope"


def overall_citations(meeting_id: str, context: dict[str, Any], highlight: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    segments = context.get("context", [])
    speakers = context.get("speaker", [])
    flags_by_segment = highlight.get("highlights", [])
    for seg_index, segment in enumerate(segments):
        flags = flags_by_segment[seg_index] if seg_index < len(flags_by_segment) else []
        for utt_index, text in enumerate(segment):
            char_flags = flags[utt_index] if utt_index < len(flags) else []
            if not any(char_flags):
                continue
            result.append({
                "citation_id": f"vcsum:{meeting_id}:seg:{seg_index}:utt:{utt_index}",
                "text": text,
                "speaker": f"speaker_{speakers[seg_index]}" if seg_index < len(speakers) else "",
                "segment_index": seg_index,
                "utterance_index": utt_index,
                "highlighted": True,
            })
    return result


def topic_citations(topic: dict[str, Any]) -> list[dict[str, Any]]:
    speakers = topic.get("speaker", [])
    return [{
        "citation_id": f"vcsum:{topic['id']}:utt:{index}",
        "text": text,
        "speaker": f"speaker_{speakers[index]}" if index < len(speakers) else "",
        "segment_id": topic["id"],
    } for index, text in enumerate(topic.get("context", []))]


def base_review(*, unit_id: str, unit_type: str, source_dataset: str, meeting_id: str, reviewed_at: str) -> dict[str, Any]:
    return {
        "schema_version": "meetingmind.ai-review.v1",
        "dataset_version": "meetingmind-real-v1",
        "annotation_status": "ai_reviewed_silver",
        "unit_id": unit_id,
        "unit_type": unit_type,
        "source_dataset": source_dataset,
        "meeting_id": meeting_id,
        "reviewer": "codex-independent-review-v1",
        "reviewed_at": reviewed_at,
        "human_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 580 个候选单元的独立 AI 初审结果")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--datasets-dir", type=Path, default=DATASETS)
    parser.add_argument("--reviewed-at", default=None, help="ISO-8601 时间；省略时使用当前 UTC 时间")
    args = parser.parse_args()
    reviewed_at = args.reviewed_at or datetime.now(timezone.utc).isoformat()

    candidate_path = args.datasets_dir / "meetingmind_real_v1_candidates.jsonl"
    source_path = args.datasets_dir / "meetingmind_real_v1_sources.jsonl"
    candidates = read_jsonl(candidate_path)
    ali_sources = read_jsonl(source_path)

    vcsum_base = args.data_root / "VCSUM" / "vcsum_data"
    contexts = {str(row["id"]): row for row in read_jsonl(vcsum_base / "overall_context.txt")}
    highlights = {str(row["id"]): row for row in read_jsonl(vcsum_base / "overall_highlights.txt")}
    topics = {str(row["id"]): row for row in read_jsonl(vcsum_base / "short_test.txt")}

    reviews: list[dict[str, Any]] = []

    for candidate in candidates:
        meeting_id = str(candidate["meeting_id"])
        task = str(candidate["task"])
        topic_id = candidate.get("topic_id")
        unit_id = f"qa:vcsum:{meeting_id}:{topic_id or task}"
        row = base_review(unit_id=unit_id, unit_type="qa", source_dataset="VCSUM", meeting_id=meeting_id, reviewed_at=reviewed_at)
        if task == "overall_summary_qa":
            corrected = overall_citations(meeting_id, contexts[meeting_id], highlights[meeting_id])
            rationale = "答案来自 VCSUM long_test 官方摘要；引用改为该会议全部官方 highlight，避免原候选最多 12 条造成漏引。"
        else:
            corrected = topic_citations(topics[str(topic_id)])
            rationale = "答案来自 VCSUM short_test 官方 discussion；引用改为该主题完整 context，避免原候选最多 6 段造成漏引。"
        original_ids = [item["citation_id"] for item in candidate.get("citations", [])]
        corrected_ids = [item["citation_id"] for item in corrected]
        row.update({
            "decision": "accept" if original_ids == corrected_ids else "edit",
            "candidate": {"task": task, "question": candidate["question"], "answer": candidate["answer"], "citation_ids": original_ids},
            "corrected": {"question": candidate["question"], "answer": candidate["answer"], "citations": corrected},
            "evidence_ids": corrected_ids,
            "rationale": rationale,
        })
        reviews.append(row)

        if task != "overall_summary_qa":
            continue
        for todo in candidate.get("todo_candidates", []):
            review = base_review(unit_id=todo["todo_id"], unit_type="todo", source_dataset="VCSUM", meeting_id=meeting_id, reviewed_at=reviewed_at)
            review.update({
                "decision": "reject",
                "candidate": todo,
                "corrected": None,
                "evidence_ids": [todo["evidence_id"]],
                "rationale": "原句属于讨论、历史陈述、身份介绍或现场主持语，未形成可验证的会后行动承诺；speaker_n 仅是数据集标签，不能推断为负责人。",
            })
            reviews.append(review)
        for constraint in candidate.get("constraints", []):
            cid = constraint["constraint_id"]
            review = base_review(unit_id=cid, unit_type="constraint", source_dataset="VCSUM", meeting_id=meeting_id, reviewed_at=reviewed_at)
            if cid in CONFIRMED_CONSTRAINTS:
                corrected = {**constraint, "kind": classify_constraint(constraint["text"]), "needs_review": False}
                review.update({
                    "decision": "accept" if corrected["kind"] == constraint["kind"] else "edit",
                    "candidate": constraint,
                    "corrected": corrected,
                    "evidence_ids": [constraint["evidence_id"]],
                    "rationale": "原文明确表达否定、阈值、范围或覆盖规则，保留完整原句以避免丢失条件。",
                })
            else:
                review.update({
                    "decision": "reject",
                    "candidate": constraint,
                    "corrected": None,
                    "evidence_ids": [constraint["evidence_id"]],
                    "rationale": "关键词命中但语义是提问、描述、残句、弱重复或一般陈述，不能稳定作为结构化约束。",
                })
            reviews.append(review)

    for source in ali_sources:
        meeting_id = str(source["meeting_id"])
        for todo in source.get("todo_candidates", []):
            tid = todo["todo_id"]
            review = base_review(unit_id=tid, unit_type="todo", source_dataset="AliMeeting-Eval", meeting_id=meeting_id, reviewed_at=reviewed_at)
            if tid in ALI_TODO_EDITS:
                corrected = [{
                    "content": content,
                    "assignee": "",
                    "deadline": "",
                    "status": "candidate",
                    "evidence_id": todo["evidence_id"],
                } for content in ALI_TODO_EDITS[tid]]
                review.update({
                    "decision": "edit",
                    "candidate": todo,
                    "corrected": corrected,
                    "evidence_ids": [todo["evidence_id"]],
                    "rationale": "原文含明确后续动作，但未明确可核验的责任人或截止时间；拆分并规范动作，相关字段留空而不猜测。",
                })
            else:
                review.update({
                    "decision": "reject",
                    "candidate": todo,
                    "corrected": None,
                    "evidence_ids": [todo["evidence_id"]],
                    "rationale": "原句是问题、回顾、建议性讨论、残句或与更明确候选重复，不能确认成独立待办。",
                })
            reviews.append(review)
        for constraint in source.get("constraints", []):
            cid = constraint["constraint_id"]
            review = base_review(unit_id=cid, unit_type="constraint", source_dataset="AliMeeting-Eval", meeting_id=meeting_id, reviewed_at=reviewed_at)
            if cid in CONFIRMED_CONSTRAINTS:
                corrected = {**constraint, "kind": classify_constraint(constraint["text"]), "needs_review": False}
                review.update({
                    "decision": "accept" if corrected["kind"] == constraint["kind"] else "edit",
                    "candidate": constraint,
                    "corrected": corrected,
                    "evidence_ids": [constraint["evidence_id"]],
                    "rationale": "原文明确表达否定、阈值、范围或条件流程；保留原句作为可追溯约束。",
                })
            else:
                review.update({
                    "decision": "reject",
                    "candidate": constraint,
                    "corrected": None,
                    "evidence_ids": [constraint["evidence_id"]],
                    "rationale": "关键词命中但未形成独立、稳定的约束，或与更完整候选重复。",
                })
            reviews.append(review)

    unit_ids = [row["unit_id"] for row in reviews]
    type_counts = Counter(row["unit_type"] for row in reviews)
    if len(reviews) != 580 or len(set(unit_ids)) != 580:
        raise RuntimeError(f"review contract mismatch: records={len(reviews)}, unique={len(set(unit_ids))}")
    if type_counts != Counter({"constraint": 228, "todo": 194, "qa": 158}):
        raise RuntimeError(f"review type counts mismatch: {dict(type_counts)}")

    output_path = args.datasets_dir / "meetingmind_real_v1_ai_reviews.jsonl"
    output_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in reviews) + "\n", encoding="utf-8")
    decision_counts = Counter((row["unit_type"], row["decision"]) for row in reviews)
    manifest = {
        "schema_version": "meetingmind.ai-review-manifest.v1",
        "dataset_version": "meetingmind-real-v1",
        "generated_at": reviewed_at,
        "annotation_status": "ai_reviewed_silver",
        "gold": False,
        "human_review_required": True,
        "human_sampling_plan": {
            "minimum_units": 20,
            "coverage": ["qa", "todo", "constraint", "VCSUM", "AliMeeting-Eval", "accept", "edit", "reject"],
            "rule": "若抽样发现系统性错误，扩大复核范围并修订规则后重新生成，不能直接提升为 gold。",
        },
        "source_hashes": {
            "sources_sha256_jsonl_lf": stable_jsonl_hash(source_path),
            "candidates_sha256_jsonl_lf": stable_jsonl_hash(candidate_path),
        },
        "counts": {
            "total": len(reviews),
            "by_unit_type": dict(sorted(type_counts.items())),
            "by_type_and_decision": {f"{kind}.{decision}": count for (kind, decision), count in sorted(decision_counts.items())},
            "qa_corrected_citations": sum(len(row["corrected"]["citations"]) for row in reviews if row["unit_type"] == "qa"),
        },
        "files": {
            "reviews": {
                "path": str(output_path.relative_to(REPO_ROOT)),
                "records": len(reviews),
                "sha256": stable_jsonl_hash(output_path),
                "sha256_bytes": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            }
        },
        "limitations": [
            "本产物是独立 AI 第一轮复核，不是人工 gold。",
            "VCSUM 的摘要答案沿用上游公开标注，未对摘要事实正确性做二次人工改写。",
            "AliMeeting 没有公开的待办与约束 gold，保留项仍需人工抽检。",
            "说话人标签只用于证据定位，不作为真实姓名或待办负责人。",
        ],
    }
    manifest_path = args.datasets_dir / "meetingmind_real_v1_ai_review_manifest.json"
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "manifest": str(manifest_path), **manifest["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
