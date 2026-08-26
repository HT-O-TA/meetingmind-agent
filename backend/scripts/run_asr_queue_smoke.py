"""用真实 PostgreSQL/Redis/RabbitMQ/FunASR 验证音频业务闭环。

脚本只创建带 ``asr-smoke-`` 前缀的临时数据，报告写完后立即清理。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.core.cache_init import close_redis, init_redis
from app.core.config import settings
from app.core.rabbitmq import rabbitmq_manager
from app.db.database import AsyncSessionLocal
from app.models.meeting import Meeting, SpeechRecord
from app.models.user import User
from app.services.task_queue import (
    TaskStatus,
    create_audio_transcribe_task,
    task_queue_service,
)
from app.workers.audio_worker import process_audio_message


async def wait_for_task(task_id: str, timeout_seconds: int = 180) -> object:
    for _ in range(timeout_seconds * 2):
        task = await task_queue_service.get_task_status(task_id)
        if task and task.status in {
            TaskStatus.COMPLETED.value,
            TaskStatus.DEAD_LETTER.value,
            TaskStatus.PUBLISH_FAILED.value,
        }:
            return task
        await asyncio.sleep(0.5)
    raise TimeoutError(f"ASR task did not finish: {task_id}")


async def run(audio: Path) -> dict:
    suffix = uuid.uuid4().hex[:10]
    username = f"asr-smoke-{suffix}"
    destination = (
        Path(settings.UPLOAD_DIR).resolve() / "audio" / "smoke" / f"{suffix}.wav"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio, destination)

    user_id = meeting_id = None
    task = None
    handle = None
    try:
        async with AsyncSessionLocal() as db:
            user = User(
                username=username,
                email=f"{username}@example.invalid",
                hashed_password="not-a-login-account",
                role="user",
                is_active=False,
            )
            db.add(user)
            await db.flush()
            meeting = Meeting(title=f"ASR smoke {suffix}", organizer_id=user.id)
            db.add(meeting)
            await db.commit()
            user_id, meeting_id = user.id, meeting.id

        await init_redis()
        handle = await rabbitmq_manager.consume_messages(
            settings.QUEUE_AUDIO_TRANSCRIBE,
            process_audio_message,
            failure_callback=task_queue_service.record_delivery_failure,
        )
        task = await create_audio_transcribe_task(
            meeting_id=meeting_id,
            file_path=str(destination),
            original_filename=audio.name,
            user_id=user_id,
            idempotency_key=f"asr-smoke-{suffix}",
            metadata={"sample_kind": "public_smoke"},
        )
        completed = await wait_for_task(task.task_id)
        if completed.status != TaskStatus.COMPLETED.value:
            raise RuntimeError(f"ASR queue smoke failed: {completed.status} {completed.error}")

        async with AsyncSessionLocal() as db:
            meeting = await db.get(Meeting, meeting_id)
            speeches = (
                await db.execute(
                    select(SpeechRecord).where(SpeechRecord.meeting_id == meeting_id)
                )
            ).scalars().all()
            return {
                "schema_version": "meetingmind.asr-queue-smoke.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sample_kind": "public_smoke",
                "task_status": completed.status,
                "task_attempt_count": completed.attempt_count,
                "meeting_persisted": bool(meeting and meeting.raw_transcript),
                "transcript": meeting.raw_transcript if meeting else None,
                "metadata_schema": (
                    meeting.transcript_metadata.get("schema_version")
                    if meeting and meeting.transcript_metadata else None
                ),
                "speech_record_count": len(speeches),
                "timestamps_preserved": bool(speeches) and all(
                    speech.start_time_offset is not None and speech.end_time_offset is not None
                    for speech in speeches
                ),
                "speaker_labels_preserved": bool(speeches) and all(
                    speech.speaker_name.startswith("speaker_") for speech in speeches
                ),
                "minutes_is_review_draft": bool(
                    meeting and meeting.minutes and "人工核验" in meeting.minutes
                ),
                "limitations": [
                    "公开单句样例，不是会议领域数据。",
                    "临时用户、会议和发言记录已在报告生成后清理。",
                ],
            }
    finally:
        if handle is not None:
            await handle.close()
        await rabbitmq_manager.close()
        if task is not None:
            await task_queue_service.delete_task(task.task_id, user_id=user_id)
        await close_redis()
        async with AsyncSessionLocal() as db:
            if meeting_id is not None:
                await db.execute(delete(SpeechRecord).where(SpeechRecord.meeting_id == meeting_id))
                await db.execute(delete(Meeting).where(Meeting.id == meeting_id))
            if user_id is not None:
                await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        destination.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args.audio.resolve(strict=True)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
