"""感知输入层 - 本地多模态证据入口

设计目标（对应 docs/总结.md 第一层）：
1. 三类附件来源（文档库上传、会议附件、Agent附件）统一经过接入治理
2. 媒体类型路由按文件类型分发到对应感知管线
3. 图片路径：Qwen3-VL 结构化提取
4. 音频路径：WAV 校验 → 统一 FunASR 适配器
5. 视频路径：ffprobe 校验 → 双路并行（画面 Qwen3-VL + 音轨 FunASR）→ 音画融合
6. 三条路径产出格式一致：带来源的非可信 Markdown 证据
7. 降级处理：模型缺失、无音轨、解码失败、Prompt Injection

外部依赖（当前为骨架预留）：
- Qwen3-VL：图片/视频画面结构化提取
- FunASR：音频 ASR + VAD + 标点恢复 + 句级时间戳 + CAM++ 匿名说话人聚类
- FFmpeg/ffprobe：视频媒体信息校验与音频抽取
- soundfile/soxr：音频格式标准化
"""
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
from app.core.logger import app_logger


# ── 统一证据文档结构 ──────────────────────────────────────────────


class AttachmentSource(str, Enum):
    """附件来源类型"""
    DOCUMENT_LIBRARY = "document_library"  # 文档库上传
    MEETING = "meeting"                    # 会议附件
    AGENT = "agent"                        # Agent 附件


class EvidenceType(str, Enum):
    """证据类型"""
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class DegradationReason(str, Enum):
    """降级原因"""
    NONE = "none"
    MODEL_UNAVAILABLE = "model_unavailable"        # 模型缺失
    NO_AUDIO_TRACK = "no_audio_track"              # 无音轨
    DECODE_FAILURE = "decode_failure"              # 解码失败
    PROMPT_INJECTION = "prompt_injection"          # Prompt 注入
    TIMEOUT = "timeout"                            # 超时
    PARTIAL_SUCCESS = "partial_success"            # 部分成功


@dataclass
class EvidenceDocument:
    """非可信 Markdown 证据文档

    所有感知管线的统一输出格式。标注"非可信"是因为内容由模型生成，
    需要下游（RAG 检索、人工核验）做事实校验。
    """
    source_file: str                              # 来源文件名
    evidence_type: EvidenceType                   # 证据类型
    model_backend: str                           # 模型后端（如 qwen3-vl / funasr / fallback）
    timestamp: str                               # 处理时间戳 ISO 格式
    markdown_content: str                         # 非可信 Markdown 正文
    speakers: List[Dict[str, Any]] = field(default_factory=list)    # 说话人列表（音频/视频）
    verifiable_facts: List[str] = field(default_factory=list)       # 可核验事实
    decisions: List[str] = field(default_factory=list)             # 决策项
    todos: List[str] = field(default_factory=list)                 # 待办项
    uncertainties: List[str] = field(default_factory=list)         # 不确定项
    degradation_info: Dict[str, Any] = field(default_factory=dict)  # 降级信息
    metadata: Dict[str, Any] = field(default_factory=dict)         # 其他元数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "evidence_type": self.evidence_type.value,
            "model_backend": self.model_backend,
            "timestamp": self.timestamp,
            "markdown_content": self.markdown_content,
            "speakers": self.speakers,
            "verifiable_facts": self.verifiable_facts,
            "decisions": self.decisions,
            "todos": self.todos,
            "uncertainties": self.uncertainties,
            "degradation_info": self.degradation_info,
            "metadata": self.metadata,
        }


# ── 接入治理模块 ──────────────────────────────────────────────────


class IntakeGovernance:
    """接入治理模块

    对三类附件来源统一做：
    1. 格式校验（MIME 白名单 + 文件大小）
    2. 安全检查（Prompt Injection 检测、恶意文件扫描）
    """

    # MIME 白名单
    ALLOWED_MIME = {
        "image/png", "image/jpeg", "image/webp", "image/gif",
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/m4a", "audio/ogg", "audio/flac",
        "video/mp4", "video/quicktime", "video/x-msvideo",
        "application/pdf",
    }

    MAX_SIZE_MB = {
        EvidenceType.IMAGE: 10,
        EvidenceType.AUDIO: 100,
        EvidenceType.VIDEO: 500,
        EvidenceType.DOCUMENT: 50,
    }

    INJECTION_PATTERNS = [
        "ignore previous", "忽略以上", "system:", "你现在是",
        "请忽略", "disregard", "override instructions",
    ]

    @classmethod
    def validate(
        cls,
        filename: str,
        content: bytes,
        content_type: Optional[str],
        source: AttachmentSource,
    ) -> tuple[bool, Optional[EvidenceType], Optional[str]]:
        """校验附件

        Returns:
            (是否通过, 证据类型, 拒绝原因)
        """
        # 1. MIME 校验
        if content_type and content_type not in cls.ALLOWED_MIME:
            return False, None, f"不支持的 MIME 类型: {content_type}"

        # 2. 证据类型推断
        evidence_type = cls._infer_evidence_type(filename, content_type)
        if evidence_type is None:
            return False, None, f"无法识别文件类型: {filename}"

        # 3. 大小校验
        size_mb = len(content) / (1024 * 1024)
        limit = cls.MAX_SIZE_MB.get(evidence_type, 50)
        if size_mb > limit:
            return False, evidence_type, f"文件过大: {size_mb:.1f}MB > {limit}MB"

        # 4. Prompt Injection 检测（对文本类内容做轻量检查）
        try:
            text_preview = content[:2048].decode("utf-8", errors="ignore").lower()
            for pattern in cls.INJECTION_PATTERNS:
                if pattern.lower() in text_preview:
                    return False, evidence_type, f"检测到 Prompt 注入: {pattern}"
        except Exception:
            pass

        return True, evidence_type, None

    @staticmethod
    def _infer_evidence_type(
        filename: str, content_type: Optional[str]
    ) -> Optional[EvidenceType]:
        if content_type:
            if content_type.startswith("image/"):
                return EvidenceType.IMAGE
            if content_type.startswith("audio/"):
                return EvidenceType.AUDIO
            if content_type.startswith("video/"):
                return EvidenceType.VIDEO
            if "pdf" in content_type:
                return EvidenceType.DOCUMENT
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        image_exts = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
        audio_exts = {"mp3", "wav", "m4a", "ogg", "flac"}
        video_exts = {"mp4", "mov", "avi", "mkv"}
        doc_exts = {"pdf", "docx", "txt", "md"}
        if ext in image_exts:
            return EvidenceType.IMAGE
        if ext in audio_exts:
            return EvidenceType.AUDIO
        if ext in video_exts:
            return EvidenceType.VIDEO
        if ext in doc_exts:
            return EvidenceType.DOCUMENT
        return None


# ── 图片感知管线 ──────────────────────────────────────────────────


class ImagePerception:
    """图片感知管线

    使用 Qwen3-VL 对图片做结构化提取，输出：
    - 摘要、OCR 文字、视觉事实、决策项、待办项、不确定项

    外部依赖：Qwen3-VL（API 或本地部署）
    """

    MODEL_BACKEND = "qwen3-vl"

    # 结构化提取 Prompt（要求模型返回 JSON schema）
    EXTRACTION_PROMPT = """请对这张图片做结构化提取，返回 JSON：
{
  "summary": "图片摘要",
  "ocr_text": "图中文字（OCR）",
  "visual_facts": ["可核验的视觉事实"],
  "decisions": ["图中显示的决策项"],
  "todos": ["图中显示的待办项"],
  "uncertainties": ["无法确定的内容"]
}"""

    async def extract(
        self,
        filename: str,
        content: bytes,
    ) -> EvidenceDocument:
        """对图片做结构化提取

        TODO: 接入 Qwen3-VL API 或本地部署模型
        当前返回降级证据。
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())

        try:
            extraction = await self._call_qwen3_vl(content)
            markdown = self._build_markdown(filename, extraction)
            return EvidenceDocument(
                source_file=filename,
                evidence_type=EvidenceType.IMAGE,
                model_backend=self.MODEL_BACKEND,
                timestamp=timestamp,
                markdown_content=markdown,
                verifiable_facts=extraction.get("visual_facts", []),
                decisions=extraction.get("decisions", []),
                todos=extraction.get("todos", []),
                uncertainties=extraction.get("uncertainties", []),
            )
        except Exception as e:
            app_logger.warning(f"[ImagePerception] Qwen3-VL 调用失败，降级: {e}")
            return self._degrade(filename, timestamp, str(e))

    async def _call_qwen3_vl(self, content: bytes) -> Dict[str, Any]:
        """调用 Qwen3-VL 模型

        TODO: 实现实际的模型调用
        - 方式1：通过 DashScope API 调用 qwen-vl-max
        - 方式2：本地部署 Qwen3-VL，通过 HTTP 推理
        """
        raise NotImplementedError("Qwen3-VL 集成待实现（需配置 API key 或本地部署）")

    def _build_markdown(self, filename: str, extraction: Dict[str, Any]) -> str:
        """构建非可信 Markdown 证据"""
        parts = [f"# 图片证据：{filename}\n"]
        parts.append(f"> ⚠️ 非可信证据：由 {self.MODEL_BACKEND} 生成，需人工核验\n")
        if extraction.get("summary"):
            parts.append(f"## 摘要\n{extraction['summary']}\n")
        if extraction.get("ocr_text"):
            parts.append(f"## OCR 文字\n```\n{extraction['ocr_text']}\n```\n")
        if extraction.get("visual_facts"):
            parts.append("## 视觉事实\n" + "\n".join(f"- {f}" for f in extraction["visual_facts"]))
        return "\n".join(parts)

    def _degrade(self, filename: str, timestamp: str, reason: str) -> EvidenceDocument:
        """降级：模型不可用时返回降级证据"""
        return EvidenceDocument(
            source_file=filename,
            evidence_type=EvidenceType.IMAGE,
            model_backend="fallback",
            timestamp=timestamp,
            markdown_content=f"# 图片证据（降级）：{filename}\n> ⚠️ 模型不可用，仅记录文件元信息\n",
            degradation_info={
                "reason": DegradationReason.MODEL_UNAVAILABLE.value,
                "detail": reason,
            },
        )


# ── 音频感知管线 ──────────────────────────────────────────────────


class AudioPerception:
    """音频感知管线

    流程：WAV 校验 → 统一 FunASR 服务 → 版本化证据。
    MP3/M4A 和视频音轨仍延后到 ffmpeg 进入受管部署以后。
    """

    MODEL_BACKEND = "funasr"
    TARGET_SAMPLE_RATE = 16000  # 标准化采样率

    async def transcribe(
        self,
        filename: str,
        content: bytes,
    ) -> EvidenceDocument:
        """音频转写与匿名说话人聚类。"""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
        temp_path: Optional[Path] = None
        try:
            if Path(filename).suffix.lower() != ".wav":
                raise ValueError("音频感知正式路径当前只支持 WAV")
            from app.services.asr_service import funasr_service

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
                temporary.write(content)
                temp_path = Path(temporary.name)
            result = await funasr_service.transcribe(temp_path)
            return EvidenceDocument(
                source_file=filename,
                evidence_type=EvidenceType.AUDIO,
                model_backend=f"funasr:{result.model}",
                timestamp=timestamp,
                markdown_content=result.to_evidence_markdown(filename),
                speakers=[item.model_dump(mode="json") for item in result.speakers],
                uncertainties=result.uncertainties,
                metadata=result.model_dump(mode="json", exclude={"text", "segments"}),
            )
        except Exception as e:
            app_logger.warning(f"[AudioPerception] FunASR 调用失败，降级: {e}")
            return self._degrade(filename, timestamp, str(e))
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _degrade(self, filename: str, timestamp: str, reason: str) -> EvidenceDocument:
        return EvidenceDocument(
            source_file=filename,
            evidence_type=EvidenceType.AUDIO,
            model_backend="fallback",
            timestamp=timestamp,
            markdown_content=f"# 音频证据（降级）：{filename}\n> ⚠️ 模型不可用，仅记录文件元信息\n",
            degradation_info={
                "reason": DegradationReason.MODEL_UNAVAILABLE.value,
                "detail": reason,
            },
        )


# ── 视频感知管线（双路并行 + 音画融合）────────────────────────────


class VideoPerception:
    """视频感知管线

    流程：
    1. ffprobe 校验媒体信息
    2. 双路并行：
       - 画面侧：抽帧 → Qwen3-VL 提取摘要/OCR/时间线
       - 音轨侧：FFmpeg 抽音频 → FunASR 转写+说话人分离
    3. 音画融合：按时间戳对齐画面事件和语音片段
    4. 输出统一非可信 Markdown 证据

    外部依赖：ffprobe/FFmpeg, Qwen3-VL, FunASR
    """

    MODEL_BACKEND = "qwen3-vl+funasr"

    def __init__(self):
        self._image_perception = ImagePerception()
        self._audio_perception = AudioPerception()

    async def process(
        self,
        filename: str,
        content: bytes,
    ) -> EvidenceDocument:
        """视频双路处理 + 音画融合

        TODO: 实现 ffprobe 校验和 FFmpeg 抽音轨
        当前返回降级证据。
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())

        try:
            # 1. ffprobe 校验
            media_info = await self._probe_media(content)
            if not media_info.get("has_video"):
                raise ValueError("文件无视频轨")

            # 2. 双路并行
            import asyncio
            visual_task = self._process_visual_track(content)
            audio_task = self._process_audio_track(content, media_info)

            visual_result, audio_result = await asyncio.gather(
                visual_task, audio_task, return_exceptions=True
            )

            # 3. 音画融合
            fused = self._fuse_audio_visual(
                filename, visual_result, audio_result, media_info
            )

            # 4. 构建证据
            degradation = {}
            if isinstance(visual_result, Exception):
                degradation["visual"] = str(visual_result)
            if isinstance(audio_result, Exception):
                degradation["audio"] = str(audio_result)

            markdown = self._build_markdown(fused)

            return EvidenceDocument(
                source_file=filename,
                evidence_type=EvidenceType.VIDEO,
                model_backend=self.MODEL_BACKEND,
                timestamp=timestamp,
                markdown_content=markdown,
                speakers=fused.get("speakers", []),
                verifiable_facts=fused.get("facts", []),
                decisions=fused.get("decisions", []),
                todos=fused.get("todos", []),
                uncertainties=fused.get("uncertainties", []),
                degradation_info=degradation if degradation else {"reason": DegradationReason.NONE.value},
                metadata={"media_info": media_info},
            )
        except Exception as e:
            app_logger.warning(f"[VideoPerception] 处理失败，降级: {e}")
            return self._degrade(filename, timestamp, str(e))

    async def _probe_media(self, content: bytes) -> Dict[str, Any]:
        """使用 ffprobe 校验媒体信息

        TODO: 实现 ffprobe 调用
        返回：{"has_video": True, "has_audio": True, "duration": 120.5, "fps": 30}
        """
        raise NotImplementedError("ffprobe 集成待实现")

    async def _process_visual_track(self, content: bytes) -> Dict[str, Any]:
        """画面侧处理：抽帧 → Qwen3-VL 提取摘要/OCR/时间线

        TODO: 实现抽帧和 Qwen3-VL 调用
        """
        raise NotImplementedError("视频画面处理待实现（依赖 Qwen3-VL）")

    async def _process_audio_track(
        self, content: bytes, media_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """音轨侧处理：FFmpeg 抽音频 → FunASR 转写+说话人分离

        如果 media_info 显示无音轨，返回降级标记。
        TODO: 实现 FFmpeg 抽音轨和 FunASR 调用
        """
        if not media_info.get("has_audio"):
            return {"degraded": True, "reason": DegradationReason.NO_AUDIO_TRACK.value}
        raise NotImplementedError("视频音轨处理待实现（依赖 FFmpeg + FunASR）")

    def _fuse_audio_visual(
        self,
        filename: str,
        visual_result: Any,
        audio_result: Any,
        media_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """音画融合：按时间戳对齐画面事件和语音片段

        将画面侧的时间线事件与音轨侧的语音片段按时间戳对齐，
        合并为统一的结构化输出。
        """
        fused = {"speakers": [], "facts": [], "decisions": [], "todos": [], "uncertainties": []}

        if not isinstance(visual_result, Exception) and isinstance(visual_result, dict):
            fused["facts"].extend(visual_result.get("visual_facts", []))
            fused["decisions"].extend(visual_result.get("decisions", []))
            fused["todos"].extend(visual_result.get("todos", []))

        if not isinstance(audio_result, Exception) and isinstance(audio_result, dict):
            fused["speakers"].extend(audio_result.get("speakers", []))
            fused["facts"].extend(audio_result.get("facts", []))
            fused["decisions"].extend(audio_result.get("decisions", []))
            fused["todos"].extend(audio_result.get("todos", []))

        return fused

    def _build_markdown(self, fused: Dict[str, Any]) -> str:
        parts = ["# 视频证据（音画融合）\n"]
        parts.append(f"> ⚠️ 非可信证据：由 {self.MODEL_BACKEND} 生成，需人工核验\n")
        if fused.get("facts"):
            parts.append("## 可核验事实\n" + "\n".join(f"- {f}" for f in fused["facts"]))
        if fused.get("decisions"):
            parts.append("\n## 决策项\n" + "\n".join(f"- {d}" for d in fused["decisions"]))
        if fused.get("todos"):
            parts.append("\n## 待办项\n" + "\n".join(f"- {t}" for t in fused["todos"]))
        return "\n".join(parts)

    def _degrade(self, filename: str, timestamp: str, reason: str) -> EvidenceDocument:
        return EvidenceDocument(
            source_file=filename,
            evidence_type=EvidenceType.VIDEO,
            model_backend="fallback",
            timestamp=timestamp,
            markdown_content=f"# 视频证据（降级）：{filename}\n> ⚠️ 处理失败，仅记录文件元信息\n",
            degradation_info={
                "reason": DegradationReason.DECODE_FAILURE.value,
                "detail": reason,
            },
        )


# ── 感知管线入口（媒体类型路由）──────────────────────────────────


class PerceptionPipeline:
    """感知管线入口

    接收经过接入治理的附件，按媒体类型路由到对应感知管线，
    输出统一的 EvidenceDocument。
    """

    def __init__(self):
        self._image = ImagePerception()
        self._audio = AudioPerception()
        self._video = VideoPerception()

    async def process(
        self,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        source: AttachmentSource = AttachmentSource.DOCUMENT_LIBRARY,
    ) -> EvidenceDocument:
        """处理附件：治理 → 路由 → 感知 → 证据文档"""
        # 1. 接入治理
        ok, evidence_type, reason = IntakeGovernance.validate(
            filename, content, content_type, source
        )
        if not ok:
            return EvidenceDocument(
                source_file=filename,
                evidence_type=EvidenceType.DOCUMENT,
                model_backend="governance_reject",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
                markdown_content=f"# 接入治理拒绝：{filename}\n> 拒绝原因：{reason}\n",
                degradation_info={"reason": DegradationReason.PROMPT_INJECTION.value, "detail": reason},
            )

        # 2. 媒体类型路由
        if evidence_type == EvidenceType.IMAGE:
            return await self._image.extract(filename, content)
        elif evidence_type == EvidenceType.AUDIO:
            return await self._audio.transcribe(filename, content)
        elif evidence_type == EvidenceType.VIDEO:
            return await self._video.process(filename, content)
        else:
            # 文档类走原有 document_parser
            return EvidenceDocument(
                source_file=filename,
                evidence_type=EvidenceType.DOCUMENT,
                model_backend="document_parser",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
                markdown_content=f"# 文档证据：{filename}\n> 由 document_parser 处理\n",
            )


_pipeline_instance: Optional[PerceptionPipeline] = None


def get_perception_pipeline() -> PerceptionPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = PerceptionPipeline()
    return _pipeline_instance
