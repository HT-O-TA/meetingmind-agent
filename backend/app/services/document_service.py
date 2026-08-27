import os
import json
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, delete, or_
from fastapi import UploadFile
from werkzeug.utils import secure_filename
from app.models.document import Document
from app.models.vector import VectorChunk
from app.core.config import settings
from app.core.exceptions import AppException
from app.services.text_process_service import TextProcessService
from app.services.embedding_service import EmbeddingService
from app.services.document_parser import DocumentParser
from app.services.input_admission import FileAdmissionError, input_admission_policy
from app.core.security import is_admin_user, require_write_user
from app.models.user import User
import math


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.text_process_service = TextProcessService()
        self._embedding_service = None  # 懒加载
        self.document_parser = DocumentParser()
    
    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    async def get_by_id(self, doc_id: int) -> Document:
        result = await self.db.execute(
            select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise AppException("文档不存在", 404)
        return doc

    async def get_for_user(self, doc_id: int, user: User, *, write: bool = False) -> Document:
        doc = await self.get_by_id(doc_id)
        if write:
            require_write_user(user)
            allowed = is_admin_user(user) or doc.uploader_id == user.id
        else:
            same_department = bool(user.department) and doc.department == user.department
            allowed = (
                is_admin_user(user)
                or bool(doc.is_public)
                or doc.uploader_id == user.id
                or same_department
            )
        if not allowed:
            raise AppException("无权访问该文档", 403)
        return doc

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        file_type: Optional[str] = None,
        status: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> Tuple[List[Document], int, int]:
        """
        获取文档列表
        
        Returns:
            Tuple[文档列表, 总数, 总页数]
        """
        if current_user is None:
            raise AppException("需要登录后访问文档", 401)
        query = select(Document).where(Document.deleted_at.is_(None))
        if not is_admin_user(current_user):
            access_rules = [
                Document.is_public.is_(True),
                Document.uploader_id == current_user.id,
            ]
            if current_user.department:
                access_rules.append(
                    and_(Document.department.is_not(None), Document.department == current_user.department)
                )
            query = query.where(or_(*access_rules))
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
        
        try:
            ext = input_admission_policy.validate_document_metadata(
                filename,
                getattr(file, "content_type", None),
                settings.allowed_file_extensions_list,
            )
        except FileAdmissionError as exc:
            app_logger.warning("文档准入拒绝: %s: %s", filename, exc)
            raise AppException(str(exc), exc.status_code) from exc

        # 创建上传目录（使用绝对路径）
        upload_dir = settings.UPLOAD_DIR_ABSOLUTE
        os.makedirs(upload_dir, exist_ok=True)
        
        # 安全处理文件名
        safe_original_name = secure_filename(filename) if filename else "unnamed"
        if not safe_original_name:
            safe_original_name = "unnamed"
        safe_name = f"{os.urandom(8).hex()}_{safe_original_name}"
        file_path = os.path.join(upload_dir, safe_name)

        # 读取文件内容
        try:
            await file.seek(0)
            file_bytes = await file.read()
            app_logger.debug(f"读取文件完成: {filename}, 大小: {len(file_bytes)} bytes")
        except Exception as e:
            app_logger.exception(f"文件读取错误: {filename}: {e}")
            raise AppException("读取文件失败", 500)

        try:
            input_admission_policy.validate_size(
                len(file_bytes), settings.MAX_FILE_SIZE, label="文档"
            )
            input_admission_policy.validate_document_content(ext, file_bytes)
        except FileAdmissionError as exc:
            app_logger.warning("文档内容准入拒绝: %s: %s", filename, exc)
            raise AppException(str(exc), exc.status_code) from exc

        # 保存文件到磁盘
        try:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            app_logger.debug(f"文件保存成功: {file_path}")
        except Exception as e:
            app_logger.exception(f"文件保存错误: {filename}: {e}")
            raise AppException("保存文件失败", 500)

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
                is_public=False,
                content=content,
                status="parsed" if content else "uploaded",
            )
            self.db.add(doc)
            await self.db.commit()
            await self.db.refresh(doc)
            app_logger.debug(f"数据库记录创建成功: {filename} -> ID: {doc.id}")
        except Exception as e:
            app_logger.exception(f"数据库错误: {filename}: {e}")
            # 清理已保存的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            raise AppException("保存文档记录失败", 500)

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
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        为文档内容创建向量块

        Args:
            document_id: 文档ID
            content: 文档内容
            meeting_id: 会议ID（可选，用于关联）
            department: 部门（可选）
        """
        try:
            # 使用统一的 SPEAKER_AWARE_HYBRID 分块策略
            chunks, chunk_metadatas = await self._split_document_chunks(
                content=content,
                document_id=document_id,
            )

            if not chunks:
                return

            # 向量化
            embeddings = self.embedding_service.encode_batch(chunks)

            vector_chunks = []
            for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                metadata = chunk_metadatas[idx] if idx < len(chunk_metadatas) else {}
                if source_metadata:
                    metadata = {**metadata, **source_metadata}

                # 从 metadata 中提取说话人信息
                speaker_name = metadata.get('speaker_name')
                time_offset = metadata.get('start_time_offset')

                vector_chunk = VectorChunk(
                    document_id=document_id,
                    meeting_id=meeting_id,
                    chunk_text=chunk_text,
                    chunk_index=idx,
                    speaker_name=speaker_name,
                    time_offset=time_offset,
                    embedding=json.dumps(embedding),
                    embedding_array=embedding,
                    embedding_model=(
                        "fallback-word-frequency-v1"
                        if self.embedding_service.use_fallback
                        else settings.EMBEDDING_MODEL_NAME
                    ),
                    department=department,
                    metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                )
                vector_chunks.append(vector_chunk)

            if vector_chunks:
                self.db.add_all(vector_chunks)
                await self.db.commit()

        except Exception as e:
            import logging
            logging.error(f"Failed to create vector chunks for document {document_id}: {e}")

    async def _split_document_chunks(
        self,
        content: str,
        document_id: int,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        统一使用 SPEAKER_AWARE_HYBRID 分块策略

        策略特性：
        - 说话人感知 + 语义连贯性混合分块
        - 语气词过滤
        - 无说话人信息时自动回退为纯语义分块
        """
        try:
            from app.services.semantic_chunker import (
                ChunkingConfig,
                SemanticChunker,
            )

            chunking_config = ChunkingConfig(
                min_chunk_size=settings.SEMANTIC_CHUNK_MIN_SIZE,
                max_chunk_size=settings.SEMANTIC_CHUNK_MAX_SIZE,
                chunk_overlap=settings.SEMANTIC_CHUNK_OVERLAP,
                semantic_threshold=settings.SEMANTIC_CHUNK_THRESHOLD,
            )

            semantic_chunker = SemanticChunker(config=chunking_config)
            semantic_chunks = await semantic_chunker.chunk_document(
                content,
                doc_id=str(document_id),
            )

            chunks = [chunk.content for chunk in semantic_chunks if chunk.content and chunk.content.strip()]
            metadatas = [
                {
                    **chunk.metadata,
                    "chunk_id": chunk.chunk_id,
                    "chunking": "semantic",
                    "strategy": "speaker_aware_hybrid",
                    "use_llm": False,
                }
                for chunk in semantic_chunks
                if chunk.content and chunk.content.strip()
            ]

            if chunks:
                return chunks, metadatas

        except Exception as e:
            from app.core.logger import app_logger
            app_logger.warning(f"SPEAKER_AWARE_HYBRID分块失败，回退基础切分: document_id={document_id}, error={e}")

        # 回退到基础固定长度切分
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
        from app.services.vector_cache_manager import invalidate_document_cache

        await invalidate_document_cache(document_id)

    async def upsert_asr_evidence_document(
        self,
        *,
        meeting_id: int,
        uploader_id: int,
        department: Optional[str],
        original_filename: str,
        content: str,
        task_id: str,
        evidence_version: int,
        audio_sha256: str,
    ) -> Document:
        """只在 ASR 完成且存在安全文本时创建/重建可检索证据。"""
        if not content.strip():
            raise ValueError("安全 ASR 证据为空，不能创建检索文档")

        result = await self.db.execute(
            select(Document).where(
                Document.meeting_id == meeting_id,
                Document.file_type == "asr_evidence",
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            document = Document(
                meeting_id=meeting_id,
                uploader_id=uploader_id,
                filename=f"meeting_{meeting_id}_asr_evidence.md",
                original_filename=f"{original_filename}.transcript.md",
                file_path=f"evidence://meeting/{meeting_id}/asr",
                file_size=len(content.encode("utf-8")),
                file_type="asr_evidence",
                department=department,
                is_public=False,
                content=content,
                status="parsed",
            )
            self.db.add(document)
            await self.db.commit()
            await self.db.refresh(document)
        else:
            document.uploader_id = uploader_id
            document.department = department
            document.original_filename = f"{original_filename}.transcript.md"
            document.file_size = len(content.encode("utf-8"))
            document.content = content
            document.status = "parsed"
            await self.db.commit()
            await self.db.refresh(document)
            await self._delete_vector_chunks(document.id)

        await self._create_vector_chunks(
            document.id,
            content,
            meeting_id=meeting_id,
            department=department,
            source_metadata={
                "source_type": "asr_evidence",
                "source_task_id": task_id,
                "evidence_version": evidence_version,
                "audio_sha256": audio_sha256,
            },
        )
        return document

    async def invalidate_asr_evidence_document(
        self, meeting_id: int, reason: str
    ) -> Optional[int]:
        """清除旧 ASR 检索块，避免失败/全隔离结果以空文档参与 RAG。"""
        result = await self.db.execute(
            select(Document).where(
                Document.meeting_id == meeting_id,
                Document.file_type == "asr_evidence",
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            return None
        document.content = None
        document.file_size = 0
        document.status = "failed"
        await self.db.commit()
        await self._delete_vector_chunks(document.id)
        from app.core.logger import app_logger

        app_logger.warning(
            "ASR 证据索引已失效 meeting_id=%s document_id=%s reason=%s",
            meeting_id,
            document.id,
            reason,
        )
        return document.id

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
        is_public: Optional[bool] = None,
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
        if is_public is not None:
            doc.is_public = is_public
        
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
        
        # 数据库删除使用同一事务；提交成功后再尽力清理物理文件。
        await self.db.execute(delete(VectorChunk).where(VectorChunk.document_id == doc_id))
        await self.db.delete(doc)
        await self.db.commit()
        try:
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
        except OSError as exc:
            from app.core.logger import app_logger

            app_logger.warning(f"文档记录已删除，但物理文件清理失败: {doc.file_path}: {exc}")

    async def get_vector_chunks(self, doc_id: int) -> List[VectorChunk]:
        """获取文档的所有向量块"""
        result = await self.db.execute(
            select(VectorChunk).where(VectorChunk.document_id == doc_id).order_by(VectorChunk.chunk_index)
        )
        return result.scalars().all()


async def get_all_document_chunks(db: AsyncSession) -> List[Dict[str, Any]]:
    """获取所有文档块（用于知识图谱构建等场景）"""
    result = await db.execute(
        select(VectorChunk).order_by(VectorChunk.document_id, VectorChunk.chunk_index)
    )
    chunks = result.scalars().all()
    
    return [
        {
            "chunk_text": chunk.chunk_text,
            "document_id": chunk.document_id,
            "meeting_id": chunk.meeting_id,
            "speaker_name": chunk.speaker_name,
            "time_offset": chunk.time_offset,
            "metadata": json.loads(chunk.metadata_json) if chunk.metadata_json else {},
        }
        for chunk in chunks
    ]
