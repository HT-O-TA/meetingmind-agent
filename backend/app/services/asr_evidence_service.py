"""ASR 证据的安全筛选、版本元数据和可索引文本。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.services.asr_service import ASRResult, ASRSegment
from app.services.prompt_injection_guard import PromptInjectionGuard, get_prompt_injection_guard


def text_sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds or 0.0) * 1000)))
    minutes, remainder = divmod(total_ms, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


@dataclass(frozen=True)
class ScreenedASRSegment:
    index: int
    segment: ASRSegment
    security_status: str
    security_reason: Optional[str]
    content_sha256: str


@dataclass(frozen=True)
class ASRScreeningResult:
    segments: list[ScreenedASRSegment]

    @property
    def safe_segments(self) -> list[ScreenedASRSegment]:
        return [item for item in self.segments if item.security_status != "quarantined"]

    @property
    def quarantined_segments(self) -> list[ScreenedASRSegment]:
        return [item for item in self.segments if item.security_status == "quarantined"]

    @property
    def safe_transcript(self) -> str:
        return "\n".join(item.segment.text for item in self.safe_segments).strip()

    @property
    def index_text(self) -> str:
        return format_index_text(item.segment for item in self.safe_segments)

    def security_metadata(self) -> dict[str, Any]:
        quarantined = [
            {
                "segment_index": item.index,
                "speaker": item.segment.speaker,
                "start_seconds": item.segment.start_seconds,
                "end_seconds": item.segment.end_seconds,
                "content_sha256": item.content_sha256,
                "reason": item.security_reason,
            }
            for item in self.quarantined_segments
        ]
        warning_count = sum(
            item.security_status == "warning" for item in self.segments
        )
        if not self.segments:
            overall = "empty"
        elif not self.safe_segments:
            overall = "quarantined"
        elif quarantined or warning_count:
            overall = "warning"
        else:
            overall = "passed"
        return {
            "status": overall,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "method": "prompt_injection_rules_v1",
            "segment_count": len(self.segments),
            "safe_segment_count": len(self.safe_segments),
            "warning_segment_count": warning_count,
            "quarantined_segment_count": len(quarantined),
            "quarantined_segments": quarantined,
        }


def format_index_text(segments: Iterable[Any]) -> str:
    """生成说话人感知分块器可识别的文本，不包含被隔离片段。"""
    lines = []
    for item in segments:
        if isinstance(item, ASRSegment):
            start = item.start_seconds
            speaker = item.speaker
            content = item.text
        else:
            start = getattr(item, "start_time_offset", 0.0) or 0.0
            speaker = getattr(item, "speaker_name", "speaker_unknown")
            content = getattr(item, "content", "")
        content = str(content or "").strip()
        if content:
            lines.append(f"[{_timestamp(float(start))}] {speaker}: {content}")
    return "\n".join(lines)


async def screen_asr_result(
    result: ASRResult,
    guard: Optional[PromptInjectionGuard] = None,
) -> ASRScreeningResult:
    """把 ASR 片段视为不可信外部证据，逐段执行间接注入规则。"""
    guard = guard or get_prompt_injection_guard()
    screened: list[ScreenedASRSegment] = []
    for index, segment in enumerate(result.segments, start=1):
        check = await guard.check(segment.text, llm_service=None)
        if check.should_block:
            status = "quarantined"
        elif check.should_warn:
            status = "warning"
        else:
            status = "passed"
        reason = check.injection_type.value if check.injection_type else None
        screened.append(
            ScreenedASRSegment(
                index=index,
                segment=segment,
                security_status=status,
                security_reason=reason,
                content_sha256=text_sha256(segment.text),
            )
        )
    return ASRScreeningResult(screened)


def _revision_history(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    history = list(metadata.get("revision_history") or [])
    current_hash = metadata.get("current_transcript_sha256")
    if current_hash:
        history.append(
            {
                "revision": int(metadata.get("evidence_version") or 0),
                "transcript_sha256": current_hash,
                "task_id": metadata.get("task_id"),
                "review_status": (metadata.get("review") or {}).get("status"),
                "superseded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return history[-20:]


def build_asr_metadata(
    *,
    result: ASRResult,
    screening: ASRScreeningResult,
    task_id: str,
    meeting_id: int,
    original_filename: str,
    source_metadata: Optional[dict[str, Any]],
    evidence_version: int,
    previous_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """构造可追溯且向后兼容的 ASR 元数据。"""
    previous = dict(previous_metadata or {})
    source = dict(source_metadata or {})
    security = screening.security_metadata()
    safe_text = screening.safe_transcript
    metadata = {
        "schema_version": "meetingmind.asr-evidence.v2",
        "task_id": task_id,
        "evidence_id": f"meeting:{meeting_id}:asr:{task_id}",
        "evidence_version": evidence_version,
        "source_filename": original_filename,
        "source_content_type": source.get("content_type"),
        "source_size_bytes": source.get("size_bytes"),
        "provider": result.provider,
        "model": result.model,
        "vad_model": result.vad_model,
        "punctuation_model": result.punctuation_model,
        "speaker_model": result.speaker_model,
        "package_version": result.package_version,
        "device": result.device,
        "audio_sha256": result.audio_sha256,
        "original_transcript_sha256": text_sha256(result.text),
        "current_transcript_sha256": text_sha256(safe_text),
        "duration_seconds": result.duration_seconds,
        "sample_rate_hz": result.sample_rate_hz,
        "channels": result.channels,
        "latency_seconds": result.latency_seconds,
        "model_load_seconds": result.initialization_seconds,
        "inference_seconds": result.inference_seconds,
        "realtime_factor": result.realtime_factor,
        "timestamp_source": result.timestamp_source,
        "diarization_available": result.diarization_available,
        "speakers": [speaker.model_dump(mode="json") for speaker in result.speakers],
        "uncertainties": result.uncertainties,
        "security": security,
        "review": {
            "status": "requires_human_review",
            "corrected_by": None,
            "corrected_at": None,
            "reason": None,
        },
        "index": {
            "status": "pending" if screening.index_text else "not_created",
            "document_id": None,
            "indexed_revision": None,
            "reason": (
                "no_speech_detected"
                if not screening.segments
                else "all_segments_quarantined"
                if not screening.index_text
                else None
            ),
        },
        "revision_history": _revision_history(previous),
    }
    return metadata


def apply_human_correction_metadata(
    metadata: Optional[dict[str, Any]],
    *,
    corrected_text: str,
    revision: int,
    user_id: Optional[int],
    reason: str,
) -> dict[str, Any]:
    updated = dict(metadata or {})
    updated["revision_history"] = _revision_history(updated)
    updated["evidence_version"] = revision
    updated["current_transcript_sha256"] = text_sha256(corrected_text)
    updated["review"] = {
        "status": "human_corrected",
        "corrected_by": user_id,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    index = dict(updated.get("index") or {})
    index.update(
        {
            "status": "invalidated",
            "indexed_revision": None,
            "reason": "transcript_corrected",
        }
    )
    updated["index"] = index
    return updated


__all__ = [
    "ASRScreeningResult",
    "ScreenedASRSegment",
    "apply_human_correction_metadata",
    "build_asr_metadata",
    "format_index_text",
    "screen_asr_result",
    "text_sha256",
]
