import os
import json
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from fastapi import UploadFile
from werkzeug.utils import secure_filename
from app.models.document import Document
from app.models.vector import VectorChunk
from app.core.config import settings
from app.core.exceptions import AppException
from app.services.text_process_service import TextProcessService
from app.services.embedding_service import EmbeddingService
from app.services.document_parser import DocumentParser
import math


# 从配置中获取允许的文件类型
ALLOWED_TYPES = set(settings.allowed_file_extensions_list) | {"mp3", "mp4", "wav"}  # 添加音频视频格式


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.text_process_service = TextProcessService()
        self.embedding_service = EmbeddingService()
        self.document_parser = DocumentParser()

    def _get_runtime_config(self, key: str, fallback: Any) -> Any:
        """读取配置中心运行时配置，失败时回退到 settings。"""
        try:
            from app.core.config_center import get_config
            return get_config(key, fallback)
        except Exception:
            return fallback

    async def get_by_id(self, doc_id: int) -> Document:
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise AppException("文档不存在", 404)
        return doc

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        file_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[Document], int, int]:
        """
        获取文档列表
        
        Returns:
            Tuple[文档列表, 总数, 总页数]
        """
        query = select(Document)
        if meeting_id:
            query = query.where(Document.meeting_id == meeting_id)
        if department:
            query = query.where(Document.department == department)
        if file_type:
            query = query.where(Document.file_type == file_type)
        if status:
            query = query.where(Document.status == status)

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar()
        query = query.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        docs = (await self.db.execute(query)).scalars().all()
        return docs, total, math.ceil(total / page_size) if total else 0

    async def upload(
        self,
        file: UploadFile,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        uploader_id: Optional[int] = None,
    ) -> Document:
        from app.core.logger import app_logger
        
        filename = file.filename or "unknown"
        app_logger.debug(f"处理文件: {filename}")
        
        # 检查文件类型
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_TYPES:
            error_msg = f"不支持的文件类型: {ext}"
            app_logger.error(f"文件类型错误: {filename} -> {error_msg}")
            raise AppException(error_msg, 400)

        # 创建上传目录
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        # 安全处理文件名
        safe_original_name = secure_filename(filename) if filename else "unnamed"
        if not safe_original_name:
            safe_original_name = "unnamed"
        safe_name = f"{os.urandom(8).hex()}_{safe_original_name}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_name)

        # 读取文件内容
        try:
            await file.seek(0)
            file_bytes = await file.read()
            app_logger.debug(f"读取文件完成: {filename}, 大小: {len(file_bytes)} bytes")
        except Exception as e:
            error_msg = f"读取文件失败: {str(e)}"
            app_logger.error(f"文件读取错误: {filename} -> {error_msg}")
            raise AppException(error_msg, 500)

        # 检查文件大小
        if len(file_bytes) > settings.MAX_FILE_SIZE:
            max_size_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
            error_msg = f"文件大小超过限制({max_size_mb}MB)"
            app_logger.error(f"文件大小超限: {filename} ({len(file_bytes)} bytes) -> {error_msg}")
            raise AppException(error_msg, 400)

        # 保存文件到磁盘
        try:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            app_logger.debug(f"文件保存成功: {file_path}")
        except Exception as e:
            error_msg = f"保存文件失败: {str(e)}"
            app_logger.error(f"文件保存错误: {filename} -> {error_msg}")
            raise AppException(error_msg, 500)

        file_size = len(file_bytes)

        # 解析文本内容
        content = None
        parse_metadata = {}
        try:
            parsed = self.document_parser.parse(file_bytes, ext, filename=filename)
            content = parsed.content.strip() if parsed.content else None
            parse_metadata = parsed.metadata
            if content:
                app_logger.debug(
                    f"文档解析成功: {filename}, parser={parse_metadata.get('parser')}, 内容长度: {len(content)}"
                )
            else:
                app_logger.info(f"文档未解析出文本内容: {filename}, metadata={parse_metadata}")
        except AppException:
            raise
        except Exception as e:
            app_logger.warning(f"文档解析失败: {filename} -> {str(e)}")
            parse_metadata = {"parser": "failed", "error": str(e)}

        # 创建数据库记录
        try:
            doc = Document(
                meeting_id=meeting_id,
                uploader_id=uploader_id,
                filename=safe_name,
                original_filename=safe_original_name,
                file_path=file_path,
                file_size=file_size,
                file_type=ext,
                department=department,
                content=content,
                status="parsed" if content else "uploaded",
            )
            self.db.add(doc)
            await self.db.commit()
            await self.db.refresh(doc)
            app_logger.debug(f"数据库记录创建成功: {filename} -> ID: {doc.id}")
        except Exception as e:
            error_msg = f"数据库操作失败: {str(e)}"
            app_logger.error(f"数据库错误: {filename} -> {error_msg}")
            # 清理已保存的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            raise AppException(error_msg, 500)

        # 生成向量
        if content:
            try:
                app_logger.debug(f"开始生成向量: {filename}")
                await self._create_vector_chunks(doc.id, content, meeting_id=meeting_id, department=department)
                app_logger.debug(f"向量生成完成: {filename}")
            except Exception as e:
                app_logger.warning(f"向量生成失败（不影响文档上传）: {filename} -> {str(e)}")

        app_logger.debug(f"文件上传完成: {filename} -> ID: {doc.id}")
        return doc

    async def _create_vector_chunks(
        self,
        document_id: int,
        content: str,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        speech_records: Optional[List[dict]] = None,
    ) -> None:
        """
        为文档内容创建向量块
        
        Args:
            document_id: 文档ID
            content: 文档内容
            meeting_id: 会议ID（可选）
            department: 部门（可选）
            speech_records: 预解析的发言记录列表（可选）
        """
        from app.models.meeting import SpeechRecord
        
        try:
            vector_chunks = []
            speech_record_objects = []
            
            if settings.CHUNK_MODE == "speaker" and not speech_records:
                speech_records = self.text_process_service.parse_speech_text(content)
            
            if speech_records and len(speech_records) > 0:
                # 按说话人发言切分
                chunks = [speech['content'] for speech in speech_records]
                embeddings = self.embedding_service.encode_batch(chunks)
                
                for idx, (speech, embedding) in enumerate(zip(speech_records, embeddings)):
                    metadata = {
                        'speaker_name': speech.get('speaker_name'),
                        'timestamp': speech.get('timestamp'),
                        'start_time_offset': speech.get('start_time_offset'),
                    }
                    vector_chunk = VectorChunk(
                        document_id=document_id,
                        meeting_id=meeting_id,
                        chunk_text=speech['content'],
                        chunk_index=idx,
                        speaker_name=speech.get('speaker_name'),
                        time_offset=speech.get('start_time_offset'),
                        embedding=json.dumps(embedding),
                        embedding_array=embedding,
                        embedding_model=settings.EMBEDDING_MODEL,
                        department=department,
                        metadata_json=json.dumps(metadata),
                    )
                    vector_chunks.append(vector_chunk)
                    
                    # 创建发言记录（无论是否有会议ID）
                    speech_record = SpeechRecord(
                        meeting_id=meeting_id,  # 允许为 None
                        speaker_name=speech.get('speaker_name', ''),
                        content=speech['content'],
                        start_time_offset=speech.get('start_time_offset'),
                        sequence=idx,
                    )
                    speech_record_objects.append(speech_record)
            else:
                # 普通文档切分：配置启用时使用语义/层级分块，否则使用基础固定长度切分。
                chunks, chunk_metadatas = await self._split_document_chunks(
                    content=content,
                    document_id=document_id,
                )
                
                if not chunks:
                    return
                
                embeddings = self.embedding_service.encode_batch(chunks)
                
                for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                    metadata = chunk_metadatas[idx] if idx < len(chunk_metadatas) else {}
                    vector_chunk = VectorChunk(
                        document_id=document_id,
                        meeting_id=meeting_id,
                        chunk_text=chunk_text,
                        chunk_index=idx,
                        embedding=json.dumps(embedding),
                        embedding_array=embedding,
                        embedding_model=settings.EMBEDDING_MODEL,
                        department=department,
                        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    )
                    vector_chunks.append(vector_chunk)
            
            if vector_chunks:
                self.db.add_all(vector_chunks)
                
            if speech_record_objects:
                self.db.add_all(speech_record_objects)
                
            if vector_chunks or speech_record_objects:
                await self.db.commit()
            
        except Exception as e:
            # 向量存储失败不影响文档上传，但记录日志
            import logging
            logging.error(f"Failed to create vector chunks for document {document_id}: {e}")

    async def _split_document_chunks(
        self,
        content: str,
        document_id: int,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """根据配置选择普通文档切分策略"""
        enable_semantic_chunking = self._get_runtime_config(
            "processing.enable_semantic_chunking",
            settings.ENABLE_SEMANTIC_CHUNKING,
        )

        if not enable_semantic_chunking:
            chunks = self.text_process_service.split_chunks(content)
            return chunks, [{} for _ in chunks]

        try:
            from app.services.semantic_chunker import (
                ChunkingConfig,
                ChunkingStrategy,
                HierarchicalChunker,
                SemanticChunker,
            )

            strategy_value = self._get_runtime_config(
                "processing.semantic_chunk_strategy",
                settings.SEMANTIC_CHUNK_STRATEGY,
            )
            try:
                strategy = ChunkingStrategy(strategy_value)
            except ValueError:
                strategy = ChunkingStrategy.SEMANTIC_HYBRID

            use_llm = self._get_runtime_config(
                "processing.semantic_chunk_use_llm",
                settings.SEMANTIC_CHUNK_USE_LLM,
            )
            preserve_structure = self._get_runtime_config(
                "processing.semantic_chunk_preserve_structure",
                settings.SEMANTIC_CHUNK_PRESERVE_STRUCTURE,
            )

            chunking_config = ChunkingConfig(
                strategy=strategy,
                min_chunk_size=self._get_runtime_config(
                    "processing.semantic_chunk_min_size",
                    settings.SEMANTIC_CHUNK_MIN_SIZE,
                ),
                max_chunk_size=self._get_runtime_config(
                    "processing.semantic_chunk_max_size",
                    settings.SEMANTIC_CHUNK_MAX_SIZE,
                ),
                chunk_overlap=self._get_runtime_config(
                    "processing.semantic_chunk_overlap",
                    settings.SEMANTIC_CHUNK_OVERLAP,
                ),
                use_llm_split=use_llm,
                preserve_structure=preserve_structure,
                build_hierarchy=self._get_runtime_config(
                    "processing.semantic_chunk_build_hierarchy",
                    settings.SEMANTIC_CHUNK_BUILD_HIERARCHY,
                ),
            )
            semantic_chunker = SemanticChunker(config=chunking_config)

            metadata = {
                "chunking": "semantic",
                "strategy": strategy.value,
                "use_llm": use_llm,
            }

            if preserve_structure:
                semantic_chunks = await HierarchicalChunker(semantic_chunker).chunk_with_hierarchy(
                    content,
                    doc_id=str(document_id),
                    metadata=metadata,
                )
            else:
                semantic_chunks = await semantic_chunker.chunk_document(
                    content,
                    doc_id=str(document_id),
                    metadata=metadata,
                )

            chunks = [chunk.content for chunk in semantic_chunks if chunk.content and chunk.content.strip()]
            metadatas = [
                {
                    **chunk.metadata,
                    "chunk_id": chunk.chunk_id,
                    "parent_id": chunk.parent_id,
                    "child_ids": chunk.child_ids,
                    "level": chunk.level,
                }
                for chunk in semantic_chunks
                if chunk.content and chunk.content.strip()
            ]

            if chunks:
                return chunks, metadatas
        except Exception as e:
            from app.core.logger import app_logger
            app_logger.warning(f"语义分块失败，回退基础切分: document_id={document_id}, error={e}")

        chunks = self.text_process_service.split_chunks(content)
        return chunks, [{"chunking": "fixed_fallback"} for _ in chunks]

    async def _delete_vector_chunks(self, document_id: int) -> None:
        """
        删除文档的所有向量块
        
        Args:
            document_id: 文档ID
        """
        await self.db.execute(
            delete(VectorChunk).where(VectorChunk.document_id == document_id)
        )
        await self.db.commit()

    async def _update_vector_chunks_metadata(
        self,
        document_id: int,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
    ) -> None:
        """
        更新文档向量块的元数据（会议ID、部门）
        
        Args:
            document_id: 文档ID
            meeting_id: 会议ID（可选）
            department: 部门（可选）
        """
        from sqlalchemy import update
        await self.db.execute(
            update(VectorChunk)
            .where(VectorChunk.document_id == document_id)
            .values(meeting_id=meeting_id, department=department)
        )
        await self.db.commit()

    async def update_content(self, doc_id: int, content: str) -> Document:
        """
        更新文档内容
        
        注意：此方法会删除旧的向量块并创建新的向量块
        """
        doc = await self.get_by_id(doc_id)
        doc.content = content
        doc.status = "parsed"
        await self.db.commit()
        await self.db.refresh(doc)
        
        # 删除旧的向量块
        await self._delete_vector_chunks(doc.id)
        
        # 重新生成向量
        await self._create_vector_chunks(doc.id, content, meeting_id=doc.meeting_id, department=doc.department)
        
        return doc

    async def update_document_metadata(
        self,
        doc_id: int,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
    ) -> Document:
        """
        更新文档的元数据（会议ID、部门），并同步更新向量块
        
        Args:
            doc_id: 文档ID
            meeting_id: 新的会议ID（可选）
            department: 新的部门（可选）
        """
        doc = await self.get_by_id(doc_id)
        
        # 更新文档元数据
        if meeting_id is not None:
            doc.meeting_id = meeting_id
        if department is not None:
            doc.department = department
        
        await self.db.commit()
        await self.db.refresh(doc)
        
        # 同步更新向量块的元数据
        await self._update_vector_chunks_metadata(
            doc.id,
            meeting_id=doc.meeting_id,
            department=doc.department
        )
        
        return doc

    async def delete(self, doc_id: int) -> None:
        """
        删除文档及其关联的向量块
        
        Returns:
            None
        """
        doc = await self.get_by_id(doc_id)
        
        # 删除关联的向量块
        await self._delete_vector_chunks(doc_id)
        
        # 删除物理文件
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
            
        # 删除文档记录
        await self.db.delete(doc)
        await self.db.commit()

    async def get_vector_chunks(self, doc_id: int) -> List[VectorChunk]:
        """获取文档的所有向量块"""
        result = await self.db.execute(
            select(VectorChunk).where(VectorChunk.document_id == doc_id).order_by(VectorChunk.chunk_index)
        )
        return result.scalars().all()
