"""多模态服务 - 支持图片、语音等输入"""
import base64
import io
import asyncio
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


class MediaType(str, Enum):
    """媒体类型"""
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


@dataclass
class MediaContent:
    """媒体内容"""
    media_type: MediaType
    content: Union[str, bytes]
    format: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MultimodalResult:
    """多模态处理结果"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    processing_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ImageProcessor:
    """图片处理器"""
    
    SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
    MAX_SIZE_MB = 10
    
    def __init__(self):
        self._vision_client = None
    
    def _get_vision_client(self):
        """获取视觉客户端"""
        if self._vision_client is None:
            try:
                from openai import OpenAI
                api_key = settings.VISION_API_KEY
                api_base = settings.VISION_API_BASE
                
                if api_key:
                    self._vision_client = OpenAI(api_key=api_key, base_url=api_base)
                else:
                    app_logger.warning("Vision API key not configured")
                    return None
            except ImportError:
                app_logger.warning("OpenAI client not available")
                return None
        return self._vision_client
    
    async def describe_image(
        self,
        image: MediaContent,
        prompt: str = "请详细描述这张图片的内容"
    ) -> MultimodalResult:
        """
        描述图片内容
        
        Args:
            image: 图片内容
            prompt: 描述提示词
            
        Returns:
            图片描述结果
        """
        import time
        start_time = time.time()
        
        try:
            if image.format.lower() not in self.SUPPORTED_FORMATS:
                return MultimodalResult(
                    success=False,
                    error=f"不支持的图片格式: {image.format}"
                )
            
            size_mb = len(image.content) / (1024 * 1024) if isinstance(image.content, bytes) else 0
            if size_mb > self.MAX_SIZE_MB:
                return MultimodalResult(
                    success=False,
                    error=f"图片大小超过限制: {size_mb:.1f}MB > {self.MAX_SIZE_MB}MB"
                )
            
            client = self._get_vision_client()
            if client is None:
                return MultimodalResult(
                    success=False,
                    error="视觉客户端不可用"
                )
            
            if isinstance(image.content, bytes):
                base64_image = base64.b64encode(image.content).decode("utf-8")
            else:
                base64_image = image.content
            
            response = client.chat.completions.create(
                model=settings.VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image.format};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=settings.VISION_MAX_TOKENS
            )
            
            description = response.choices[0].message.content
            
            return MultimodalResult(
                success=True,
                result={"description": description},
                processing_time=time.time() - start_time
            )
        
        except Exception as e:
            app_logger.error(f"Image description failed: {e}")
            return MultimodalResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    async def extract_text(
        self,
        image: MediaContent,
        language: str = "zh+en"
    ) -> MultimodalResult:
        """
        从图片中提取文字（OCR）
        
        Args:
            image: 图片内容
            language: 识别语言
            
        Returns:
            提取的文字结果
        """
        import time
        start_time = time.time()
        
        try:
            client = self._get_vision_client()
            if client is None:
                return MultimodalResult(
                    success=False,
                    error="视觉客户端不可用"
                )
            
            if isinstance(image.content, bytes):
                base64_image = base64.b64encode(image.content).decode("utf-8")
            else:
                base64_image = image.content
            
            prompt = f"请提取图片中的所有文字，使用{language}语言返回。"
            
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image.format};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4000
            )
            
            extracted_text = response.choices[0].message.content
            
            return MultimodalResult(
                success=True,
                result={"text": extracted_text, "language": language},
                processing_time=time.time() - start_time
            )
        
        except Exception as e:
            app_logger.error(f"OCR failed: {e}")
            return MultimodalResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    async def analyze_chart(
        self,
        image: MediaContent
    ) -> MultimodalResult:
        """
        分析图表内容
        
        Args:
            image: 图表图片
            
        Returns:
            图表分析结果
        """
        import time
        start_time = time.time()
        
        try:
            client = self._get_vision_client()
            if client is None:
                return MultimodalResult(
                    success=False,
                    error="视觉客户端不可用"
                )
            
            if isinstance(image.content, bytes):
                base64_image = base64.b64encode(image.content).decode("utf-8")
            else:
                base64_image = image.content
            
            prompt = """请分析这张图表，提取以下信息：
            1. 图表类型（折线图、柱状图、饼图等）
            2. 标题和坐标轴标签
            3. 主要数据点和趋势
            4. 关键结论
            请用结构化的JSON格式返回。"""
            
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image.format};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000
            )
            
            analysis = response.choices[0].message.content
            
            return MultimodalResult(
                success=True,
                result={"analysis": analysis},
                processing_time=time.time() - start_time
            )
        
        except Exception as e:
            app_logger.error(f"Chart analysis failed: {e}")
            return MultimodalResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )


class AudioProcessor:
    """音频处理器"""
    
    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "ogg", "flac"}
    MAX_SIZE_MB = 50
    MAX_DURATION_SECONDS = 600
    
    def __init__(self):
        self._whisper_client = None
    
    def _get_whisper_client(self):
        """获取 Whisper 客户端"""
        if self._whisper_client is None:
            try:
                from openai import OpenAI
                api_key = settings.WHISPER_API_KEY
                api_base = settings.WHISPER_API_BASE
                
                if api_key:
                    self._whisper_client = OpenAI(api_key=api_key, base_url=api_base)
                else:
                    app_logger.warning("Whisper API key not configured")
                    return None
            except ImportError:
                app_logger.warning("OpenAI client not available")
                return None
        return self._whisper_client
    
    async def transcribe(
        self,
        audio: MediaContent,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> MultimodalResult:
        """
        音频转文字（语音识别）
        
        Args:
            audio: 音频内容
            language: 音频语言（可选，自动检测）
            task: 任务类型（transcribe/translate）
            
        Returns:
            转写结果
        """
        import time
        start_time = time.time()
        
        try:
            if audio.format.lower() not in self.SUPPORTED_FORMATS:
                return MultimodalResult(
                    success=False,
                    error=f"不支持的音频格式: {audio.format}"
                )
            
            size_mb = len(audio.content) / (1024 * 1024) if isinstance(audio.content, bytes) else 0
            if size_mb > self.MAX_SIZE_MB:
                return MultimodalResult(
                    success=False,
                    error=f"音频大小超过限制: {size_mb:.1f}MB > {self.MAX_SIZE_MB}MB"
                )
            
            client = self._get_whisper_client()
            if client is None:
                return MultimodalResult(
                    success=False,
                    error="语音识别客户端不可用"
                )
            
            audio_file = io.BytesIO(audio.content) if isinstance(audio.content, bytes) else audio.content
            
            response = client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=audio_file,
                language=language,
                response_format="verbose_json"
            )
            
            return MultimodalResult(
                success=True,
                result={
                    "text": response.text,
                    "language": response.language,
                    "duration": getattr(response, "duration", None)
                },
                processing_time=time.time() - start_time
            )
        
        except Exception as e:
            app_logger.error(f"Transcription failed: {e}")
            return MultimodalResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    async def translate_audio(
        self,
        audio: MediaContent
    ) -> MultimodalResult:
        """
        翻译音频内容为英文
        
        Args:
            audio: 音频内容
            
        Returns:
            翻译结果
        """
        import time
        start_time = time.time()
        
        try:
            client = self._get_whisper_client()
            if client is None:
                return MultimodalResult(
                    success=False,
                    error="语音识别客户端不可用"
                )
            
            audio_file = io.BytesIO(audio.content) if isinstance(audio.content, bytes) else audio.content
            
            response = client.audio.translations.create(
                model="whisper-1",
                file=audio_file
            )
            
            return MultimodalResult(
                success=True,
                result={"text": response.text},
                processing_time=time.time() - start_time
            )
        
        except Exception as e:
            app_logger.error(f"Audio translation failed: {e}")
            return MultimodalResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )


class MultimodalService:
    """多模态服务 - 统一入口"""
    
    def __init__(self):
        self._image_processor = ImageProcessor()
        self._audio_processor = AudioProcessor()
    
    @property
    def image_processor(self) -> ImageProcessor:
        """获取图片处理器"""
        return self._image_processor
    
    @property
    def audio_processor(self) -> AudioProcessor:
        """获取音频处理器"""
        return self._audio_processor
    
    async def process_content(
        self,
        content: MediaContent
    ) -> MultimodalResult:
        """
        处理多模态内容
        
        Args:
            content: 媒体内容
            
        Returns:
            处理结果
        """
        if content.media_type == MediaType.IMAGE:
            return await self._image_processor.describe_image(content)
        elif content.media_type == MediaType.AUDIO:
            return await self._audio_processor.transcribe(content)
        else:
            return MultimodalResult(
                success=False,
                error=f"不支持的媒体类型: {content.media_type}"
            )
    
    async def process_batch(
        self,
        contents: List[MediaContent]
    ) -> List[MultimodalResult]:
        """
        批量处理多模态内容
        
        Args:
            contents: 媒体内容列表
            
        Returns:
            处理结果列表
        """
        tasks = [self.process_content(content) for content in contents]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def extract_from_meeting_materials(
        self,
        materials: List[MediaContent]
    ) -> Dict[str, Any]:
        """
        从会议材料中提取信息
        
        Args:
            materials: 会议材料列表（可能包含图片、音频等）
            
        Returns:
            提取的信息汇总
        """
        results = {
            "images": [],
            "audio": [],
            "errors": []
        }
        
        for material in materials:
            if material.media_type == MediaType.IMAGE:
                result = await self._image_processor.describe_image(material)
                if result.success:
                    results["images"].append(result.result)
                else:
                    results["errors"].append({
                        "type": "image",
                        "error": result.error
                    })
            
            elif material.media_type == MediaType.AUDIO:
                result = await self._audio_processor.transcribe(material)
                if result.success:
                    results["audio"].append(result.result)
                else:
                    results["errors"].append({
                        "type": "audio",
                        "error": result.error
                    })
        
        return results
    
    def get_supported_formats(self) -> Dict[str, List[str]]:
        """获取支持的格式"""
        return {
            "image": list(ImageProcessor.SUPPORTED_FORMATS),
            "audio": list(AudioProcessor.SUPPORTED_FORMATS)
        }


_multimodal_service: Optional[MultimodalService] = None


def get_multimodal_service() -> MultimodalService:
    """获取多模态服务"""
    global _multimodal_service
    if _multimodal_service is None:
        _multimodal_service = MultimodalService()
    return _multimodal_service
