import wave

import pytest

from app.core.config import settings
from app.services.asr_service import FunASRService, InvalidAudioError, inspect_wav
from app.evaluation.asr_metrics import character_error_rate, word_error_rate
from app.services.task_queue import TaskQueueService, TaskType
from app.workers.audio_worker import _draft_outputs, _safe_audio_path


class FakeFunASRModel:
    def generate(self, **kwargs):
        assert kwargs["input"].endswith(".wav")
        return [{
            "text": "张三负责提交报告。",
            "sentence_info": [{
                "start": 120,
                "end": 980,
                "text": "张三负责提交报告。",
                "spk": 0,
            }],
        }]


def write_wav(path, seconds=1):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * int(16000 * seconds))


@pytest.mark.asyncio
async def test_funasr_result_preserves_timestamps_speakers_and_provenance(tmp_path):
    audio = tmp_path / "meeting.wav"
    write_wav(audio)
    result = await FunASRService(model=FakeFunASRModel()).transcribe(audio)

    assert result.schema_version == "meetingmind.asr-evidence.v1"
    assert result.text == "张三负责提交报告。"
    assert result.segments[0].start_seconds == 0.12
    assert result.segments[0].end_seconds == 0.98
    assert result.segments[0].speaker == "speaker_0"
    assert result.diarization_available is True
    assert len(result.audio_sha256) == 64
    assert "匿名聚类标签" in "".join(result.uncertainties)


def test_wav_validation_rejects_disguised_file(tmp_path):
    fake = tmp_path / "fake.wav"
    fake.write_bytes(b"not-a-wave")
    with pytest.raises(InvalidAudioError):
        inspect_wav(fake)


def test_audio_worker_path_is_confined_to_managed_upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    managed = tmp_path / "uploads" / "audio" / "7" / "safe.wav"
    managed.parent.mkdir(parents=True)
    write_wav(managed)
    assert _safe_audio_path(str(managed)) == managed.resolve()

    outside = tmp_path / "outside.wav"
    write_wav(outside)
    with pytest.raises(PermissionError):
        _safe_audio_path(str(outside))


def test_rule_outputs_are_labeled_as_draft():
    _, minutes, candidates = _draft_outputs("张三负责提交测试报告。")
    assert "规则抽取" in minutes
    assert "人工核验" in minutes
    assert candidates


def test_audio_task_has_dedicated_queue(monkeypatch):
    monkeypatch.setattr(settings, "QUEUE_AUDIO_TRANSCRIBE", "audio.test")
    assert TaskQueueService()._get_task_queue(TaskType.AUDIO_TRANSCRIBE) == "audio.test"


def test_asr_metrics_have_frozen_normalization_rules():
    assert character_error_rate("你好，世界！", "你好世界") == 0.0
    assert character_error_rate("甲乙丙", "甲丁丙") == pytest.approx(1 / 3)
    assert word_error_rate("张三 提交 报告", "张三 提交 报告", "zh") == 0.0
