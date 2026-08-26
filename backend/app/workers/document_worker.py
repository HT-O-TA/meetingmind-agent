"""文档处理Worker - 消费消息队列中的任务"""
import logging
import hashlib
from typing import Dict, Any

from app.core.rabbitmq import rabbitmq_manager
from app.core.config import settings
from app.services.task_queue import (
    task_queue_service,
    TaskStatus,
    create_vector_embed_task,
)
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DocumentWorker:
    """文档处理Worker"""

    def __init__(self):
        self.is_running = False

    async def process_document(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理文档"""
        try:
            document_id = payload.get("document_id")
            file_path = payload.get("file_path")
            user_id = payload.get("user_id")

            logger.info(f"Processing document {document_id}, file: {file_path}")

            # 更新状态为处理中
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=10
            )

            # 1. 解析文档并更新向量块
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=20
            )

            from app.db.database import AsyncSessionLocal
            from app.services.document_parser import DocumentParser

            async with AsyncSessionLocal() as db:
                doc_service = DocumentService(db)
                # 获取文档记录
                doc = await doc_service.get_by_id(document_id)
                # 如果文档内容尚未解析，则解析文件
                if not doc.content and file_path:
                    parser = DocumentParser()
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
                    parsed = parser.parse(file_bytes, ext, filename=file_path)
                    if parsed.content:
                        await doc_service.update_content(document_id, parsed.content)
                # 获取向量块
                chunks = await doc_service.get_vector_chunks(document_id)

            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=50
            )

            # 2. 创建向量化任务
            chunk_ids = [chunk.id for chunk in chunks]
            
            # 如果有 chunk，触发向量化
            if chunk_ids:
                # 先更新进度
                await task_queue_service.update_task_status(
                    task_id,
                    TaskStatus.PROCESSING,
                    progress=70
                )
                
                # 触发向量化任务
                vector_task = await create_vector_embed_task(
                    document_id=document_id,
                    chunk_ids=chunk_ids,
                    user_id=user_id,
                    idempotency_key=self._child_idempotency_key(
                        "vector", document_id, chunk_ids
                    ),
                )
                if vector_task.status == TaskStatus.PUBLISH_FAILED.value:
                    raise RuntimeError(
                        f"Vector child task publish failed: {vector_task.task_id}"
                    )
                
                await task_queue_service.update_task_status(
                    task_id,
                    TaskStatus.PROCESSING,
                    progress=90
                )
            
            # 完成
            result = {
                "document_id": document_id,
                "chunks_created": len(chunks),
                "chunk_ids": chunk_ids,
                "vector_task_id": vector_task.task_id if chunk_ids else None,
                "message": "Document processed successfully"
            }
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                progress=100,
                result=result
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=str(e)
            )
            raise

    @staticmethod
    def _child_idempotency_key(kind: str, document_id: int, chunk_ids: list[int]) -> str:
        digest = hashlib.sha256(
            ",".join(str(item) for item in sorted(chunk_ids)).encode("utf-8")
        ).hexdigest()[:16]
        return f"document:{document_id}:{kind}:{digest}"


class VectorWorker:
    """向量化Worker"""
    
    def __init__(self):
        self.embedding_service = None
        self.is_running = False
    
    async def process_vector_embed(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理向量化"""
        try:
            document_id = payload.get("document_id")
            chunk_ids = payload.get("chunk_ids", [])
            if self.embedding_service is None:
                self.embedding_service = EmbeddingService()
            
            logger.info(f"Embedding chunks for document {document_id}, count: {len(chunk_ids)}")
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=10
            )
            
            # 向量化处理
            embedded_count = 0
            failures = []
            for i, chunk_id in enumerate(chunk_ids):
                try:
                    await self.embedding_service.embed_chunk(chunk_id)
                    embedded_count += 1
                    
                    # 更新进度
                    progress = 10 + int((i + 1) / len(chunk_ids) * 80)
                    await task_queue_service.update_task_status(
                        task_id,
                        TaskStatus.PROCESSING,
                        progress=progress
                    )
                except Exception as e:
                    logger.warning(f"Failed to embed chunk {chunk_id}: {e}")
                    failures.append({"chunk_id": chunk_id, "error": str(e)})

            if failures:
                raise RuntimeError(
                    f"{len(failures)}/{len(chunk_ids)} chunks embedding failed: {failures[:3]}"
                )
            
            result = {
                "document_id": document_id,
                "total_chunks": len(chunk_ids),
                "embedded_chunks": embedded_count,
                "message": "Vector embedding completed"
            }
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                progress=100,
                result=result
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in vector embedding: {e}")
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=str(e)
            )
            raise


# Worker 实例
document_worker = DocumentWorker()
vector_worker = VectorWorker()


async def _run_claimed_task(message_body: Dict[str, Any], processor) -> Any:
    task_id = message_body.get("task_id")
    claim = await task_queue_service.claim_task(task_id)
    if claim == "terminal":
        logger.info("Skip terminal duplicate task: %s", task_id)
        return None
    if claim == "missing":
        raise ValueError(f"Task status missing: {task_id}")
    if claim == "busy":
        raise RuntimeError(f"Task already claimed: {task_id}")
    worker_id = claim.split(":", 1)[1]
    try:
        return await processor(task_id, message_body.get("payload", {}))
    finally:
        await task_queue_service.release_claim(task_id, worker_id)


async def process_document_message(message_body: Dict[str, Any]):
    """处理文档处理队列消息"""
    logger.info("Received document task: %s", message_body.get("task_id"))
    return await _run_claimed_task(message_body, document_worker.process_document)


async def process_vector_message(message_body: Dict[str, Any]):
    """处理向量化队列消息"""
    logger.info("Received vector task: %s", message_body.get("task_id"))
    return await _run_claimed_task(message_body, vector_worker.process_vector_embed)


async def start_workers():
    """启动所有Worker"""
    logger.info("Starting message queue workers...")
    
    handles = [
        await rabbitmq_manager.consume_messages(
            settings.QUEUE_DOCUMENT_PROCESS,
            process_document_message,
            failure_callback=task_queue_service.record_delivery_failure,
        ),
        await rabbitmq_manager.consume_messages(
            settings.QUEUE_VECTOR_EMBED,
            process_vector_message,
            failure_callback=task_queue_service.record_delivery_failure,
        ),
    ]
    if settings.ENABLE_ASR:
        from app.workers.audio_worker import process_audio_message

        handles.append(
            await rabbitmq_manager.consume_messages(
                settings.QUEUE_AUDIO_TRANSCRIBE,
                process_audio_message,
                failure_callback=task_queue_service.record_delivery_failure,
            )
        )
    
    logger.info("All workers started successfully")
    return handles


async def stop_workers():
    """停止所有Worker"""
    logger.info("Stopping workers...")
    document_worker.is_running = False
    vector_worker.is_running = False
    logger.info("All workers stopped")
