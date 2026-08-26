"""本地 FunASR 适配器：懒加载、结构化证据和明确的不确定性。

正式入口目前只接受 WAV。这样无需在 Web 容器里偷偷依赖 ffmpeg，也不会把
未实现的“任意格式标准化”写成已完成能力。
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import threading
import time
import wave
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import settings


ASR_SCHEMA_VERSION = "meetingmind.asr-evidence.v1"


class ASRUnavailableError(RuntimeError):
    """ASR 被关闭或可选运行依赖尚未安装。"""


class InvalidAudioError(ValueError):
    """输入不是当前正式入口支持的 WAV。"""


class ASRSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    speaker: str = "speaker_unknown"


class ASRSpeaker(BaseModel):
    speaker: str
    speech_seconds: float = Field(ge=0)


class ASRResult(BaseModel):
    schema_version: str = ASR_SCHEMA_VERSION
    provider: str = "funasr"
    model: str
    vad_model: Optional[str] = None
    punctuation_model: Optional[str] = None
    speaker_model: Optional[str] = None
    package_version: str
    device: str
    language: str = "zh"
    text: str
    segments: list[ASRSegment]
    speakers: list[ASRSpeaker]
    audio_sha256: str
    duration_seconds: float = Field(ge=0)
    sample_rate_hz: int = Field(gt=0)
    channels: int = Field(gt=0)
    latency_seconds: float = Field(ge=0)
    initialization_seconds: float = Field(ge=0)
    inference_seconds: float = Field(ge=0)
    realtime_factor: Optional[float] = Field(default=None, ge=0)
    timestamp_source: str
    diarization_available: bool
    uncertainties: list[str] = Field(default_factory=list)

    def to_evidence_markdown(self, source_name: str) -> str:
        lines = [
            f"# 音频证据：{source_name}",
            "",
            "> ⚠️ 非可信模型证据：转写和匿名说话人聚类均需人工核验。",
            "",
            "## 时间线",
            "",
        ]
        for segment in self.segments:
            lines.append(
                f"- [{segment.start_seconds:.2f}s–{segment.end_seconds:.2f}s] "
                f"**{segment.speaker}**：{segment.text}"
            )
        if self.uncertainties:
            lines.extend(["", "## 不确定性", ""])
            lines.extend(f"- {item}" for item in self.uncertainties)
        return "\n".join(lines)


def inspect_wav(path: Path) -> dict[str, Any]:
    """用标准库校验 WAV，并返回可复核的输入元数据。"""
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            sample_rate = audio.getframerate()
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
    except (wave.Error, EOFError, OSError) as exc:
        raise InvalidAudioError(f"无法解码 WAV: {exc}") from exc
    if frames <= 0 or sample_rate <= 0 or channels <= 0 or sample_width <= 0:
        raise InvalidAudioError("WAV 缺少有效音频帧")
    duration = frames / sample_rate
    return {
        "frames": frames,
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "sample_width_bytes": sample_width,
        "duration_seconds": duration,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FunASRService:
    """进程内单例模型；加载和推理串行化，队列 prefetch 控制跨任务并发。"""

    def __init__(self, model: Any = None) -> None:
        self._model = model
        self._model_lock = threading.RLock()
        self._device: Optional[str] = None

    @staticmethod
    def _package_version() -> str:
        try:
            return importlib.metadata.version("funasr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    @staticmethod
    def _choose_device() -> str:
        requested = settings.ASR_DEVICE.strip().lower()
        if requested != "auto":
            return requested
        try:
            import torch
        except ImportError:
            return "cpu"
        return "cuda:0" if torch.cuda.is_available() else "cpu"

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not settings.ENABLE_ASR:
            raise ASRUnavailableError("ENABLE_ASR=false；请显式启用本地 ASR")
        if settings.ASR_PROVIDER.strip().lower() != "funasr":
            raise ASRUnavailableError(f"不支持的 ASR_PROVIDER: {settings.ASR_PROVIDER}")
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise ASRUnavailableError(
                "未安装 FunASR；请先安装匹配 CUDA 的 PyTorch，再安装 requirements-asr.txt"
            ) from exc

        self._device = self._choose_device()
        kwargs: dict[str, Any] = {
            "model": settings.ASR_MODEL,
            "device": self._device,
            "hub": settings.ASR_HUB,
            "disable_update": True,
            "disable_pbar": True,
        }
        if settings.ASR_VAD_MODEL:
            kwargs["vad_model"] = settings.ASR_VAD_MODEL
            kwargs["vad_kwargs"] = {"max_single_segment_time": 60000}
        if settings.ASR_PUNC_MODEL:
            kwargs["punc_model"] = settings.ASR_PUNC_MODEL
        if settings.ASR_SPK_MODEL:
            kwargs["spk_model"] = settings.ASR_SPK_MODEL
        self._model = AutoModel(**kwargs)
        return self._model

    async def transcribe(self, audio_path: str | Path) -> ASRResult:
        return await asyncio.to_thread(self._transcribe_sync, Path(audio_path))

    def _transcribe_sync(self, audio_path: Path) -> ASRResult:
        path = audio_path.resolve(strict=True)
        if path.suffix.lower() != ".wav":
            raise InvalidAudioError("正式 ASR 入口当前只支持 .wav")
        if path.stat().st_size > settings.ASR_MAX_AUDIO_SIZE_BYTES:
            raise InvalidAudioError("音频超过 ASR_MAX_AUDIO_SIZE_BYTES")
        audio_info = inspect_wav(path)
        if audio_info["duration_seconds"] > settings.ASR_MAX_DURATION_SECONDS:
            raise InvalidAudioError("音频超过 ASR_MAX_DURATION_SECONDS")

        audio_sha256 = sha256_file(path)
        started = time.perf_counter()
        with self._model_lock:
            load_started = time.perf_counter()
            model = self._load_model()
            initialization_seconds = time.perf_counter() - load_started
            inference_started = time.perf_counter()
            generated = model.generate(
                input=str(path),
                batch_size_s=settings.ASR_BATCH_SIZE_S,
                use_itn=True,
            )
            inference_seconds = time.perf_counter() - inference_started
        latency = time.perf_counter() - started
        if not isinstance(generated, list) or not generated or not isinstance(generated[0], dict):
            raise RuntimeError("FunASR 返回了无法识别的结果结构")
        raw = generated[0]
        text = str(raw.get("text") or "").strip()
        segments, timestamp_source, uncertainties = self._segments_from_result(
            raw, text, audio_info["duration_seconds"]
        )
        speaker_seconds: dict[str, float] = defaultdict(float)
        for segment in segments:
            speaker_seconds[segment.speaker] += max(
                0.0, segment.end_seconds - segment.start_seconds
            )
        speakers = [
            ASRSpeaker(speaker=speaker, speech_seconds=round(seconds, 3))
            for speaker, seconds in sorted(speaker_seconds.items())
        ]
        diarization_available = any(
            segment.speaker != "speaker_unknown" for segment in segments
        )
        if diarization_available:
            uncertainties.append("speaker_N 是匿名聚类标签，不等同于真实姓名或身份")
        elif settings.ASR_SPK_MODEL:
            uncertainties.append("本次结果未返回可用的说话人标签")

        duration = float(audio_info["duration_seconds"])
        return ASRResult(
            model=settings.ASR_MODEL,
            vad_model=settings.ASR_VAD_MODEL or None,
            punctuation_model=settings.ASR_PUNC_MODEL or None,
            speaker_model=settings.ASR_SPK_MODEL or None,
            package_version=self._package_version(),
            device=self._device or self._choose_device(),
            text=text,
            segments=segments,
            speakers=speakers,
            audio_sha256=audio_sha256,
            duration_seconds=round(duration, 3),
            sample_rate_hz=int(audio_info["sample_rate_hz"]),
            channels=int(audio_info["channels"]),
            latency_seconds=round(latency, 3),
            initialization_seconds=round(initialization_seconds, 3),
            inference_seconds=round(inference_seconds, 3),
            realtime_factor=round(inference_seconds / duration, 4) if duration else None,
            timestamp_source=timestamp_source,
            diarization_available=diarization_available,
            uncertainties=uncertainties,
        )

    @staticmethod
    def _segments_from_result(
        raw: dict[str, Any], text: str, duration_seconds: float
    ) -> tuple[list[ASRSegment], str, list[str]]:
        segments: list[ASRSegment] = []
        uncertainties: list[str] = []
        sentence_info = raw.get("sentence_info")
        if isinstance(sentence_info, list):
            for item in sentence_info:
                if not isinstance(item, dict):
                    continue
                segment_text = str(item.get("text") or item.get("sentence") or "").strip()
                if not segment_text:
                    continue
                start_ms = item.get("start", 0)
                end_ms = item.get("end", start_ms)
                try:
                    start = max(0.0, float(start_ms) / 1000.0)
                    end = max(start, float(end_ms) / 1000.0)
                except (TypeError, ValueError):
                    start, end = 0.0, duration_seconds
                    uncertainties.append("至少一个句级时间戳无法解析，已回退到音频边界")
                speaker_value = item.get("spk")
                speaker = (
                    f"speaker_{speaker_value}"
                    if speaker_value is not None
                    else "speaker_unknown"
                )
                segments.append(
                    ASRSegment(
                        start_seconds=round(start, 3),
                        end_seconds=round(end, 3),
                        text=segment_text,
                        speaker=speaker,
                    )
                )
        if segments:
            return segments, "funasr.sentence_info", uncertainties

        if text:
            uncertainties.append("模型未返回句级时间戳，整段时间使用音频边界")
            return [
                ASRSegment(
                    start_seconds=0.0,
                    end_seconds=round(duration_seconds, 3),
                    text=text,
                )
            ], "audio_bounds_fallback", uncertainties
        uncertainties.append("模型没有识别出语音文本")
        return [], "none", uncertainties


funasr_service = FunASRService()
