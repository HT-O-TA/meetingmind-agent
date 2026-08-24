"""多模态网关 - 统一多模态输入处理入口

功能：
1. 格式校验（支持 png/jpg/mp3/pdf）
2. 大小限制（图片 ≤ 10MB，音频 ≤ 50MB）
3. 安全检测（调用 ContentSafetyService）
4. 内容提取（调用已有的 ImageProcessor / AudioProcessor）
5. 转换为统一文本格式
"""
import time
from typing import Optional, Dict, Any, BinaryIO, Tuple
from dataclasses import dataclass
from enum import Enum
from app.services.multimodal import (
    MultimodalService, MediaContent, MediaType, MultimodalResult
)
from app.core.logger import app_logger
from app.core.config import settings


class MultimodalStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"          # 未启用多模态
    UNSUPPORTED = "unsupported"  # 不支持的类型
    TOO_LARGE = "too_large"      # 文件过大
    UNSAFE = "unsafe"            # 安全检测失败
    PROCESSING_ERROR = "processing_error"


@dataclass
class MultimodalProcessResult:
    """多模态处理结果"""
    status: MultimodalStatus
    text_description: str = ""
    error_message: str = ""
    processing_time_ms: float = 0.0
    media_type: str = ""


class MultimodalGateway:
    """多模态网关 - 统一入口"""

    SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
    SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "m4a", "ogg", "flac"}
    SUPPORTED_DOCUMENT_FORMATS = {"pdf", "docx", "txt", "md"}

    def __init__(self):
        self._multimodal_service = None
        self._content_safety = None

    def _get_multimodal_service(self) -> Optional[MultimodalService]:
        if self._multimodal_service is None:
            try:
                from app.services.multimodal import get_multimodal_service
                self._multimodal_service = get_multimodal_service()
            except Exception as e:
                app_logger.warning(f"获取 MultimodalService 失败: {e}")
        return self._multimodal_service

    def _get_content_safety(self):
        if self._content_safety is None:
            try:
                from app.services.content_safety import get_content_safety_service
                self._content_safety = get_content_safety_service()
            except Exception as e:
                app_logger.warning(f"获取 ContentSafetyService 失败: {e}")
        return self._content_safety

    def _detect_media_type(
        self,
        filename: str,
        content_type: Optional[str] = None,
    ) -> Optional[MediaType]:
        """检测媒体类型"""
        # 从 MIME type 判断
        if content_type:
            if content_type.startswith("image/"):
                return MediaType.IMAGE
            elif content_type.startswith("audio/"):
                return MediaType.AUDIO
            elif "pdf" in content_type or "document" in content_type:
                return MediaType.DOCUMENT

        # 从文件扩展名判断
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in self.SUPPORTED_IMAGE_FORMATS:
            return MediaType.IMAGE
        elif ext in self.SUPPORTED_AUDIO_FORMATS:
            return MediaType.AUDIO
        elif ext in self.SUPPORTED_DOCUMENT_FORMATS:
            return MediaType.DOCUMENT

        return None

    def _get_size_limit(self, media_type: MediaType) -> int:
        """获取大小限制（字节）"""
        if media_type == MediaType.IMAGE:
            return getattr(settings, "MULTIMODAL_MAX_IMAGE_SIZE_MB", 10) * 1024 * 1024
        elif media_type == MediaType.AUDIO:
            return getattr(settings, "MULTIMODAL_MAX_AUDIO_SIZE_MB", 50) * 1024 * 1024
        else:
            return 50 * 1024 * 1024  # 文档默认 50MB

    def is_enabled(self) -> bool:
        """检查多模态是否启用"""
        return getattr(settings, "ENABLE_MULTIMODAL", False)

    async def process_upload(
        self,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> MultimodalProcessResult:
        """处理上传文件"""
        start_time = time.time()

        # 检查是否启用
        if not self.is_enabled():
            return MultimodalProcessResult(
                status=MultimodalStatus.SKIPPED,
                error_message="多模态功能未启用",
            )

        # 检测媒体类型
        media_type = self._detect_media_type(filename, content_type)
        if media_type is None:
            return MultimodalProcessResult(
                status=MultimodalStatus.UNSUPPORTED,
                error_message=f"不支持的文件类型: {filename}",
            )

        # 大小限制
        size_limit = self._get_size_limit(media_type)
        if len(content) > size_limit:
            size_mb = len(content) / (1024 * 1024)
            limit_mb = size_limit / (1024 * 1024)
            return MultimodalProcessResult(
                status=MultimodalStatus.TOO_LARGE,
                error_message=f"文件大小 {size_mb:.1f}MB 超过限制 {limit_mb:.0f}MB",
            )

        # 安全检测
        try:
            safety = self._get_content_safety()
            if safety:
                safety_result = await safety.check_file(content, media_type)
                if not safety_result.safe:
                    return MultimodalProcessResult(
                        status=MultimodalStatus.UNSAFE,
                        error_message=f"安全检测失败: {safety_result.reason}",
                    )
        except Exception as e:
            app_logger.warning(f"安全检测异常: {e}，继续处理")

        # 内容提取
        try:
            service = self._get_multimodal_service()
            if service is None:
                return MultimodalProcessResult(
                    status=MultimodalStatus.PROCESSING_ERROR,
                    error_message="多模态服务不可用",
                )

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            media_content = MediaContent(
                media_type=media_type,
                content=content,
                format=ext,
            )

            result = await service.process_content(media_content)

            elapsed_ms = (time.time() - start_time) * 1000

            if result.success:
                text_desc = self._generate_text_description(result, media_type)
                return MultimodalProcessResult(
                    status=MultimodalStatus.SUCCESS,
                    text_description=text_desc,
                    processing_time_ms=elapsed_ms,
                    media_type=media_type.value,
                )
            else:
                return MultimodalProcessResult(
                    status=MultimodalStatus.PROCESSING_ERROR,
                    error_message=result.error or "处理失败",
                    processing_time_ms=elapsed_ms,
                )

        except Exception as e:
            app_logger.error(f"多模态处理异常: {e}")
            return MultimodalProcessResult(
                status=MultimodalStatus.PROCESSING_ERROR,
                error_message=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    def _generate_text_description(
        self,
        result: MultimodalResult,
        media_type: MediaType,
    ) -> str:
        """生成统一的文本描述"""
        data = result.result or {}

        if media_type == MediaType.IMAGE:
            description = data.get("description", "")
            text = data.get("text", "")
            parts = []
            if description:
                parts.append(f"[图片描述]: {description}")
            if text:
                parts.append(f"[图片文字]: {text}")
            return "\n".join(parts) if parts else "[图片内容已处理]"

        elif media_type == MediaType.AUDIO:
            transcription = data.get("transcription", "")
            language = data.get("language", "")
            if transcription:
                lang_hint = f"（语言: {language}）" if language else ""
                return f"[音频转录{lang_hint}]: {transcription}"
            return "[音频内容已处理]"

        elif media_type == MediaType.DOCUMENT:
            text = data.get("text", "")
            summary = data.get("summary", "")
            parts = []
            if summary:
                parts.append(f"[文档摘要]: {summary}")
            if text:
                parts.append(f"[文档内容]: {text[:500]}")
            return "\n".join(parts) if parts else "[文档内容已处理]"

        return "[内容已处理]"


_gateway_instance: Optional[MultimodalGateway] = None


def get_multimodal_gateway() -> MultimodalGateway:
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = MultimodalGateway()
    return _gateway_instance
