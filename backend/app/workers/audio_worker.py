"""音频任务消费者：FunASR → 会议证据 → 可核验规则初稿。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from app.core.cache import cache_delete
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.meeting import Meeting, SpeechRecord
from app.models.user import User
from app.services.asr_service import funasr_service
from app.services.task_queue import TaskStatus, task_queue_service
from app.services.text_process_service import TextProcessService
from app.utils.cache_utils import make_cache_key


logger = logging.getLogger(__name__)


def _safe_audio_path(value: str) -> Path:
    path = Path(value).resolve(strict=True)
    audio_root = (Path(settings.UPLOAD_DIR) / "audio").resolve()
    try:
        path.relative_to(audio_root)
    except ValueError as exc:
        raise PermissionError("音频任务路径不在受管上传目录") from exc
    if path.suffix.lower() != ".wav":
        raise ValueError("音频任务只允许 WAV")
    return path


def _draft_outputs(transcript: str) -> tuple[str, str, list[dict[str, Any]]]:
    """规则抽取只是阶段 5 前的可复核初稿，不能标成模型质量结果。"""
    processor = TextProcessService()
    summary = processor.generate_summary(transcript, max_length=500)
    candidates = processor.extract_todo_items(transcript)
    candidate_lines = [
        f"- {item['title']}（负责人：{item.get('assignee') or '待确认'}）"
        for item in candidates
    ] or ["- 未由规则命中待办；请人工复核原始转写。"]
    minutes = "\n".join(
        [
            "# 自动纪要初稿（规则抽取，需人工核验）",
            "",
            "## 摘要",
            summary or "未生成可靠摘要，请阅读带时间戳的转写证据。",
            "",
            "## 待办候选",
            *candidate_lines,
        ]
    )
    return summary, minutes, candidates


async def process_audio_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = _safe_audio_path(str(payload.get("file_path") or ""))
    meeting_id = int(payload["meeting_id"])
    user_id = int(payload["user_id"])
    original_filename = Path(str(payload.get("original_filename") or path.name)).name

    await task_queue_service.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)
    async with AsyncSessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        user = await db.get(User, user_id)
        role = str(getattr(user, "role", "")) if user else ""
        if not meeting:
            raise LookupError("会议不存在")
        if meeting.organizer_id != user_id and role not in {"admin", "UserRole.admin"}:
            raise PermissionError("任务用户无权修改该会议")
        meeting.status = "processing"
        await db.commit()

    result = await funasr_service.transcribe(path)
    await task_queue_service.update_task_status(task_id, TaskStatus.PROCESSING, progress=75)
    summary, minutes, todo_candidates = _draft_outputs(result.text)
    evidence_markdown = result.to_evidence_markdown(original_filename)

    async with AsyncSessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise LookupError("会议在 ASR 推理期间被删除")
        # 一个会议当前只保留一版正式 ASR 证据；人工录入发言不会被删除。
        await db.execute(
            delete(SpeechRecord).where(
                SpeechRecord.meeting_id == meeting_id,
                SpeechRecord.source_type == "asr",
            )
        )
        db.add_all(
            [
                SpeechRecord(
                    meeting_id=meeting_id,
                    speaker_name=segment.speaker,
                    content=segment.text,
                    start_time_offset=segment.start_seconds,
                    end_time_offset=segment.end_seconds,
                    sequence=index,
                    source_type="asr",
                    source_task_id=task_id,
                )
                for index, segment in enumerate(result.segments, start=1)
            ]
        )
        result_data = result.model_dump(mode="json")
        meeting.raw_transcript = result.text
        meeting.summary = summary or meeting.summary
        meeting.minutes = minutes
        meeting.transcript_metadata = {
            "schema_version": result.schema_version,
            "task_id": task_id,
            "source_filename": original_filename,
            "provider": result.provider,
            "model": result.model,
            "vad_model": result.vad_model,
            "punctuation_model": result.punctuation_model,
            "speaker_model": result.speaker_model,
            "package_version": result.package_version,
            "device": result.device,
            "audio_sha256": result.audio_sha256,
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
            "postprocess": {
                "method": "extractive_rules_v1",
                "quality_status": "draft_requires_human_review",
                "todo_candidates": todo_candidates,
            },
        }
        meeting.status = "completed"
        await db.commit()

    await cache_delete(make_cache_key("meetings", "detail", meeting_id))
    task_result = {
        "meeting_id": meeting_id,
        "asr": result_data,
        "evidence_markdown": evidence_markdown,
        "minutes_status": "draft_requires_human_review",
        "todo_candidates": todo_candidates,
        "durable_fields": [
            "meetings.raw_transcript",
            "meetings.transcript_metadata",
            "meetings.minutes",
            "speech_records",
        ],
    }
    await task_queue_service.update_task_status(
        task_id, TaskStatus.COMPLETED, progress=100, result=task_result
    )
    if settings.ASR_DELETE_UPLOAD_AFTER_SUCCESS:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("ASR 上传文件清理失败 task=%s: %s", task_id, exc)
    return task_result


async def process_audio_message(message_body: dict[str, Any]) -> Any:
    task_id = str(message_body.get("task_id") or "")
    claim = await task_queue_service.claim_task(task_id)
    if claim == "terminal":
        logger.info("Skip terminal duplicate audio task: %s", task_id)
        return None
    if claim in {"missing", "busy"}:
        raise RuntimeError(f"Audio task cannot be claimed: {task_id} ({claim})")
    worker_id = claim.split(":", 1)[1]
    try:
        return await process_audio_task(task_id, message_body.get("payload", {}))
    except Exception as exc:
        await task_queue_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error=f"{exc.__class__.__name__}: {exc}",
            error_category=exc.__class__.__name__,
        )
        raise
    finally:
        await task_queue_service.release_claim(task_id, worker_id)
