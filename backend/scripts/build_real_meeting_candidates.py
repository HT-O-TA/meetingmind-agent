"""把本地 AliMeeting/VCSUM 整理成可复核的会议标注候选。

输出不是 gold 真值：VCSUM 的摘要/重点句是原始公开标注，问题和引用映射是本脚本
生成的 silver 候选；待办字段只保留为空并明确原因，避免把摘要内容硬说成行动项。
"""
from __future__ import annotations

import argparse
import json
import re
import hashlib
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPO_ROOT / "data"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_textgrid(path: Path) -> list[dict[str, Any]]:
    tier = ""
    start = end = None
    spans: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = re.match(r"\s*name = \"(.*)\"$", line)
        if name:
            tier = name.group(1)
            continue
        match = re.match(r"\s*xmin = ([0-9.]+)$", line)
        if match:
            start = float(match.group(1))
            continue
        match = re.match(r"\s*xmax = ([0-9.]+)$", line)
        if match:
            end = float(match.group(1))
            continue
        text = re.match(r"\s*text = \"(.*)\"$", line)
        if text and start is not None and end is not None and text.group(1):
            spans.append(
                {
                    "speaker": tier,
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "text": text.group(1),
                }
            )
            start = end = None
    return spans


ACTION_RE = re.compile(r"(需要|应当|应该|必须|负责|完成|计划|建议|推进|落实|跟进|安排|确保|尽快|提交|整理|核对|复核|发布|上线|控制|补充|建立|制定)")
DEADLINE_RE = re.compile(r"((?:本|下|上)周[一二三四五六日天]?|月底|年底|明天|今天|尽快|[0-9一二三四五六七八九十]+(?:天|周|个月)内|[0-9一二三四五六七八九十]+月[0-9一二三四五六七八九十]+日?(?:前|后)?)")
CONSTRAINT_RE = re.compile(r"(不要|不得|不能|不应|除非|仅限|只(?:能|看|汇总)|不超过|低于|高于|至少|预算|上限|改为|改成|改到|取消|排除)")


def extract_todo_candidates(utterances: list[dict[str, Any]], max_items: int = 8) -> list[dict[str, Any]]:
    """从原文找出疑似行动句；宁可少抓，也不把整段摘要冒充待办。"""
    results = []
    seen: set[str] = set()
    for item in utterances:
        text = " ".join(str(item.get("text", "")).split())
        if len(text) < 8 or len(text) > 240 or text in seen:
            continue
        if not ACTION_RE.search(text) or text.endswith(("吗？", "吗?", "吧？", "吧?")):
            continue
        seen.add(text)
        deadline_match = DEADLINE_RE.search(text)
        results.append(
            {
                "todo_id": f"todo:{item['citation_id']}",
                "content": text,
                "assignee": item.get("speaker"),
                "deadline": deadline_match.group(1) if deadline_match else "",
                "status": "candidate",
                "confidence": 0.35,
                "evidence_id": item["citation_id"],
                "needs_review": True,
            }
        )
        if len(results) >= max_items:
            break
    return results


def extract_constraints(utterances: list[dict[str, Any]], max_items: int = 12) -> list[dict[str, Any]]:
    results = []
    seen: set[str] = set()
    for item in utterances:
        text = " ".join(str(item.get("text", "")).split())
        if len(text) < 6 or text in seen or not CONSTRAINT_RE.search(text):
            continue
        seen.add(text)
        if any(word in text for word in ("不要", "不得", "不能", "不应", "除非", "排除", "取消")):
            kind = "negative"
        elif any(word in text for word in ("不超过", "低于", "高于", "至少", "预算", "上限")):
            kind = "threshold"
        else:
            kind = "overwrite_or_scope"
        results.append(
            {
                "constraint_id": f"constraint:{item['citation_id']}",
                "kind": kind,
                "text": text,
                "evidence_id": item["citation_id"],
                "needs_review": True,
            }
        )
        if len(results) >= max_items:
            break
    return results


def ali_sources(data_root: Path) -> list[dict[str, Any]]:
    textgrids = sorted((data_root / "Eval_Ali").glob("Eval_Ali_far/textgrid_dir/*.TextGrid"))
    rows = []
    for path in textgrids:
        session_id = path.stem
        spans = parse_textgrid(path)
        utterances = [
            {"citation_id": f"ali:{session_id}:{index:04d}", **item}
            for index, item in enumerate(spans)
        ]
        far_audio = next(
            iter(sorted((data_root / "Eval_Ali" / "Eval_Ali_far" / "audio_dir").glob(f"{session_id}_MS*.wav"))),
            None,
        )
        audio_meta: dict[str, Any] = {}
        if far_audio:
            with wave.open(str(far_audio), "rb") as wav:
                audio_meta = {
                    "duration_sec": round(wav.getnframes() / wav.getframerate(), 3),
                    "sample_rate_hz": wav.getframerate(),
                    "channels": wav.getnchannels(),
                }
        near_audio_count = len(
            list((data_root / "Eval_Ali" / "Eval_Ali_near" / "audio_dir").glob(f"{session_id}_N_*.wav"))
        )
        rows.append(
            {
                "schema_version": "meetingmind.meeting-source.v1",
                "dataset_version": "meetingmind-real-v1",
                "source_dataset": "AliMeeting-Eval",
                "source_kind": "real_public",
                "annotation_status": "gold_transcript_source",
                "meeting_id": session_id,
                "transcript_source": str(path.relative_to(REPO_ROOT)),
                "audio_source": str(far_audio.relative_to(REPO_ROOT)) if far_audio else None,
                "near_audio_count": near_audio_count,
                "audio_metadata": audio_meta,
                "utterance_count": len(spans),
                "speakers": sorted({item["speaker"] for item in spans}),
                "utterances": utterances,
                "todo_candidates": extract_todo_candidates(utterances),
                "constraints": extract_constraints(utterances),
                "labeling_note": "TextGrid 是公开语料自带转写；问题、答案、待办仍需项目标注。",
            }
        )
    return rows


def vcsum_candidates(data_root: Path, limit: int | None) -> list[dict[str, Any]]:
    base = data_root / "VCSUM" / "vcsum_data"
    contexts = {row["av_num"]: row for row in read_jsonl(base / "overall_context.txt")}
    highlights = {row["av_num"]: row for row in read_jsonl(base / "overall_highlights.txt")}
    long_test = read_jsonl(base / "long_test.txt")
    short_test = read_jsonl(base / "short_test.txt")
    topics_by_av: dict[int, list[dict[str, Any]]] = {}
    for row in short_test:
        topics_by_av.setdefault(row["av_num"], []).append(row)

    candidates: list[dict[str, Any]] = []
    for row in long_test[:limit]:
        av_num = row["av_num"]
        context = contexts[av_num]
        highlight = highlights.get(av_num, {}).get("highlights", [])
        utterances = []
        for seg_index, (segment, flags) in enumerate(zip(context.get("context", []), highlight)):
            for utt_index, (text, char_flags) in enumerate(zip(segment, flags)):
                utterances.append(
                    {
                        "citation_id": f"vcsum:{row['id']}:seg:{seg_index}:utt:{utt_index}",
                        "text": text,
                        "speaker": f"speaker_{context.get('speaker', [])[seg_index]}" if seg_index < len(context.get("speaker", [])) else "",
                        "segment_index": seg_index,
                        "utterance_index": utt_index,
                        "highlighted": bool(any(char_flags)),
                    }
                )
        citations = [item for item in utterances if item["highlighted"]]
        topics = topics_by_av.get(av_num, [])
        topic_candidates = []
        for topic in topics[:8]:
            topic_context = topic.get("context", [])
            topic_speakers = topic.get("speaker", [])
            topic_utterances = [
                {
                    "citation_id": f"vcsum:{topic['id']}:utt:{index}",
                    "text": text,
                    "speaker": f"speaker_{topic_speakers[index]}" if index < len(topic_speakers) else "",
                }
                for index, text in enumerate(topic_context)
            ]
            topic_citations = [
                {
                    "citation_id": item["citation_id"],
                    "text": item["text"],
                    "speaker": item.get("speaker", ""),
                    "segment_id": topic["id"],
                }
                for item in topic_utterances[:6]
            ]
            agenda = topic.get("agenda", "").strip()
            discussion = topic.get("discussion", "").strip()
            if agenda and discussion:
                topic_candidates.append(
                    {
                        "schema_version": "meetingmind.annotation-candidate.v1",
                        "dataset_version": "meetingmind-real-v1",
                        "source_dataset": "VCSUM",
                        "source_kind": "real_public",
                        "annotation_status": "silver",
                        "meeting_id": str(row["id"]),
                        "av_num": av_num,
                        "topic_id": topic["id"],
                        "task": "topic_qa",
                        "question": f"关于“{agenda}”，会议讨论了什么？",
                        "answer": discussion,
                        "citations": topic_citations,
                        "todo_candidates": [],
                        "constraints": [],
                        "todo_annotation_status": "not_attached_to_topic_candidate",
                        "review_required": True,
                        "review_note": "问题根据 VCSUM 主题标题生成；答案来自分段摘要，需人工核对原文引用。",
                    }
                )
        todos = extract_todo_candidates(utterances, max_items=5)
        constraints = extract_constraints(utterances, max_items=8)
        candidates.extend(
            [
                {
                    "schema_version": "meetingmind.annotation-candidate.v1",
                    "dataset_version": "meetingmind-real-v1",
                    "source_dataset": "VCSUM",
                    "source_kind": "real_public",
                    "annotation_status": "silver",
                    "meeting_id": str(row["id"]),
                    "av_num": av_num,
                    "task": "overall_summary_qa",
                    "question": "这场会议的整体结论是什么？",
                    "answer": row.get("summary", ""),
                    "citations": citations[:12],
                    "todo_candidates": todos,
                    "constraints": constraints,
                    "todo_annotation_status": "silver_heuristic_candidates",
                    "review_required": True,
                    "review_note": "问题由脚本生成；答案和重点句来自 VCSUM 公开标注，需人工检查引用是否完整。",
                },
                *topic_candidates,
            ]
        )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="生成真实会议 silver 标注候选")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--limit", type=int, default=26, help="最多处理多少场 VCSUM long_test 会议")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "backend/evaluation/datasets")
    args = parser.parse_args()
    args.data_root = args.data_root.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sources = ali_sources(args.data_root)
    candidates = vcsum_candidates(args.data_root, max(0, args.limit))
    source_path = args.output_dir / "meetingmind_real_v1_sources.jsonl"
    candidate_path = args.output_dir / "meetingmind_real_v1_candidates.jsonl"
    manifest_path = args.output_dir / "meetingmind_real_v1_review_manifest.json"
    source_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in sources) + "\n", encoding="utf-8")
    candidate_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in candidates) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "meetingmind.annotation-review-manifest.v1",
        "dataset_version": "meetingmind-real-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "annotation_status": "silver",
        "review_required": True,
        "source_counts": {
            "ali_meeting_sessions": len(sources),
            "vcsum_candidate_records": len(candidates),
            "vcsum_meetings": len({row["meeting_id"] for row in candidates}),
            "todo_candidates": sum(len(row.get("todo_candidates", [])) for row in candidates),
            "constraint_candidates": sum(len(row.get("constraints", [])) for row in candidates),
            "ali_todo_candidates": sum(len(row.get("todo_candidates", [])) for row in sources),
            "ali_constraint_candidates": sum(len(row.get("constraints", [])) for row in sources),
        },
        "files": {
            "sources": {"path": str(source_path), "sha256": sha256_file(source_path), "records": len(sources)},
            "candidates": {"path": str(candidate_path), "sha256": sha256_file(candidate_path), "records": len(candidates)},
        },
        "review_checklist": [
            "逐条确认问题是否能由会议原文回答",
            "逐条确认答案没有超出引用片段",
            "确认引用片段覆盖答案关键事实",
            "将疑似行动句改成规范待办，补齐负责人和截止时间",
            "确认否定、阈值和前后覆盖关系",
            "人工确认后把 annotation_status 从 silver 改为 gold",
        ],
        "limitations": [
            "问题由规则生成，不是人工设计；",
            "待办和约束是低置信度启发式候选，不可直接用于正式 F1；",
            "AliMeeting 只有转写真值，没有公开的问答和待办真值。",
        ],
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ali_sources": len(sources), "vcsum_candidates": len(candidates), "source_path": str(source_path), "candidate_path": str(candidate_path), "manifest_path": str(manifest_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
