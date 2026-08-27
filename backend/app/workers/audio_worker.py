"""音频任务消费者：FunASR → 会议证据 → 可核验规则初稿。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from app.core.cache import cache_delete
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.meeting import Meeting, SpeechRecord
from app.models.user import User
from app.services.asr_service import funasr_service
from app.services.asr_evidence_service import build_asr_metadata, screen_asr_result
from app.services.document_service import DocumentService
from app.services.task_queue import TaskStatus, task_queue_service
from app.services.text_process_service import TextProcessService
from app.utils.cache_utils import make_cache_key


logger = logging.getLogger(__name__)


async def _mark_transcript_failed(
    task_id: str,
    payload: dict[str, Any],
    error: Exception,
) -> None:
    """ASR 失败状态必须同时落到会议证据，不能只留在 Redis。"""
    try:
        meeting_id = int(payload.get("meeting_id"))
    except (TypeError, ValueError):
        return
    async with AsyncSessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            return
        metadata = dict(meeting.transcript_metadata or {})
        ingestion = dict(metadata.get("ingestion") or {})
        ingestion.update(
            {
                "task_id": task_id,
                "status": "failed",
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_category": error.__class__.__name__,
                "error": str(error)[:500],
            }
        )
        metadata["ingestion"] = ingestion
        meeting.transcript_metadata = metadata
        meeting.transcript_status = "failed"
        await db.commit()
    await cache_delete(make_cache_key("meetings", "detail", meeting_id))


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
    source_metadata = dict(payload.get("source_metadata") or {})

    await task_queue_service.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)
    async with AsyncSessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        user = await db.get(User, user_id)
        role = str(getattr(user, "role", "")) if user else ""
        if not meeting:
            raise LookupError("会议不存在")
        if meeting.organizer_id != user_id and role not in {"admin", "UserRole.admin"}:
            raise PermissionError("任务用户无权修改该会议")
        meeting.transcript_status = "processing"
        metadata = dict(meeting.transcript_metadata or {})
        ingestion = dict(metadata.get("ingestion") or {})
        ingestion.update(
            {
                "task_id": task_id,
                "status": "processing",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        metadata["ingestion"] = ingestion
        meeting.transcript_metadata = metadata
        await db.commit()

    result = await funasr_service.transcribe(path)
    screening = await screen_asr_result(result)
    await task_queue_service.update_task_status(task_id, TaskStatus.PROCESSING, progress=75)
    safe_transcript = screening.safe_transcript
    summary, minutes, todo_candidates = _draft_outputs(safe_transcript)
    evidence_markdown = "\n".join(
        [
            f"# 音频证据：{original_filename}",
            "",
            "> 非可信 ASR 证据；已逐段执行间接注入检查，仍需人工核验。",
            "",
            screening.index_text or "没有可进入 Agent/RAG 的安全转写片段。",
        ]
    )

    async with AsyncSessionLocal() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise LookupError("会议在 ASR 推理期间被删除")
        previous_metadata = dict(meeting.transcript_metadata or {})
        evidence_version = int(meeting.transcript_revision or 0) + 1
        metadata = build_asr_metadata(
            result=result,
            screening=screening,
            task_id=task_id,
            meeting_id=meeting_id,
            original_filename=original_filename,
            source_metadata=source_metadata,
            evidence_version=evidence_version,
            previous_metadata=previous_metadata,
        )
        metadata["ingestion"] = {
            **dict(previous_metadata.get("ingestion") or {}),
            "task_id": task_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata["postprocess"] = {
            "method": "extractive_rules_v1",
            "quality_status": "draft_requires_human_review",
            "todo_candidates": todo_candidates,
        }

        # 一个会议只保留一组当前 ASR 片段；原始全文与历史哈希另行保留。
        await db.execute(
            delete(SpeechRecord).where(
                SpeechRecord.meeting_id == meeting_id,
                SpeechRecord.source_type.in_(["asr", "asr_corrected"]),
            )
        )
        db.add_all(
            [
                SpeechRecord(
                    meeting_id=meeting_id,
                    speaker_name=item.segment.speaker,
                    content=item.segment.text,
                    start_time_offset=item.segment.start_seconds,
                    end_time_offset=item.segment.end_seconds,
                    sequence=item.index,
                    source_type="asr",
                    source_task_id=task_id,
                    security_status=item.security_status,
                    security_reason=item.security_reason,
                    content_sha256=item.content_sha256,
                )
                for item in screening.segments
            ]
        )
        meeting.asr_original_transcript = result.text
        meeting.raw_transcript = safe_transcript or None
        meeting.summary = summary or meeting.summary
        meeting.minutes = minutes
        meeting.transcript_metadata = metadata
        meeting.transcript_revision = evidence_version
        meeting.transcript_status = "completed"
        await db.commit()

        document_service = DocumentService(db)
        if screening.index_text:
            evidence_document = await document_service.upsert_asr_evidence_document(
                meeting_id=meeting_id,
                uploader_id=user_id,
                department=meeting.department,
                original_filename=original_filename,
                content=screening.index_text,
                task_id=task_id,
                evidence_version=evidence_version,
                audio_sha256=result.audio_sha256,
            )
            chunks = await document_service.get_vector_chunks(evidence_document.id)
            metadata["index"] = {
                "status": "indexed" if chunks else "rebuild_required",
                "document_id": evidence_document.id,
                "indexed_revision": evidence_version if chunks else None,
                "chunk_count": len(chunks),
                "reason": None if chunks else "no_vector_chunks_created",
            }
        else:
            invalidated_document_id = await document_service.invalidate_asr_evidence_document(
                meeting_id, "all_segments_quarantined_or_empty"
            )
            metadata["index"]["document_id"] = invalidated_document_id
        meeting.transcript_metadata = metadata
        await db.commit()

    await cache_delete(make_cache_key("meetings", "detail", meeting_id))
    result_data = result.model_dump(mode="json")
    result_data["text"] = safe_transcript
    result_data["segments"] = [
        item.segment.model_dump(mode="json") for item in screening.safe_segments
    ]
    result_data["security"] = screening.security_metadata()
    task_result = {
        "meeting_id": meeting_id,
        "asr": result_data,
        "evidence_markdown": evidence_markdown,
        "evidence_version": evidence_version,
        "evidence_document_id": metadata["index"].get("document_id"),
        "evidence_security_status": metadata["security"]["status"],
        "minutes_status": "draft_requires_human_review",
        "todo_candidates": todo_candidates,
        "durable_fields": [
            "meetings.raw_transcript",
            "meetings.asr_original_transcript",
            "meetings.transcript_status",
            "meetings.transcript_revision",
            "meetings.transcript_metadata",
            "meetings.minutes",
            "speech_records",
            "documents(asr_evidence)",
            "vector_chunks",
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
        payload = dict(message_body.get("payload") or {})
        payload["source_metadata"] = dict(message_body.get("metadata") or {})
        return await process_audio_task(task_id, payload)
    except Exception as exc:
        await _mark_transcript_failed(
            task_id,
            dict(message_body.get("payload") or {}),
            exc,
        )
        await task_queue_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error=f"{exc.__class__.__name__}: {exc}",
            error_category=exc.__class__.__name__,
        )
        raise
    finally:
        await task_queue_service.release_claim(task_id, worker_id)
