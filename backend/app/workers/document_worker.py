"""文档处理Worker - 消费消息队列中的任务"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional

from aio_pika import IncomingMessage
from app.core.rabbitmq import rabbitmq_manager
from app.core.config import settings
from app.services.task_queue import (
    task_queue_service,
    TaskStatus,
    TaskType,
    create_vector_embed_task,
    create_knowledge_graph_task
)
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DocumentWorker:
    """文档处理Worker"""
    
    def __init__(self):
        self.document_service = DocumentService()
        self.embedding_service = EmbeddingService()
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
            
            # 1. 解析文档
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=20
            )
            
            chunks = await self.document_service.process_document(
                document_id=document_id,
                file_path=file_path,
                user_id=user_id
            )
            
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
                    chunk_ids=chunk_ids
                )
                
                # 触发知识图谱构建任务
                kg_task = await create_knowledge_graph_task(
                    document_id=document_id,
                    chunk_ids=chunk_ids
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


class VectorWorker:
    """向量化Worker"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.is_running = False
    
    async def process_vector_embed(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理向量化"""
        try:
            document_id = payload.get("document_id")
            chunk_ids = payload.get("chunk_ids", [])
            
            logger.info(f"Embedding chunks for document {document_id}, count: {len(chunk_ids)}")
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=10
            )
            
            # 向量化处理
            embedded_count = 0
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


class KnowledgeGraphWorker:
    """知识图谱Worker"""
    
    def __init__(self):
        self.is_running = False
    
    async def process_knowledge_graph(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理知识图谱构建"""
        try:
            document_id = payload.get("document_id")
            chunk_ids = payload.get("chunk_ids", [])
            
            logger.info(f"Building knowledge graph for document {document_id}, chunks: {len(chunk_ids)}")
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=10
            )
            
            # TODO: 实现知识图谱构建逻辑
            # 这里暂时只做示例
            
            result = {
                "document_id": document_id,
                "chunks_processed": len(chunk_ids),
                "entities_extracted": 0,
                "relations_extracted": 0,
                "message": "Knowledge graph building completed"
            }
            
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                progress=100,
                result=result
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in knowledge graph building: {e}")
            await task_queue_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=str(e)
            )
            raise


# Worker 实例
document_worker = DocumentWorker()
vector_worker = VectorWorker()
knowledge_graph_worker = KnowledgeGraphWorker()


async def process_document_message(message: IncomingMessage):
    """处理文档处理队列消息"""
    async with message.process():
        try:
            body = json.loads(message.body.decode())
            task_id = body.get("task_id")
            payload = body.get("payload", {})
            
            logger.info(f"Received document task: {task_id}")
            
            await document_worker.process_document(task_id, payload)
            
        except Exception as e:
            logger.error(f"Error processing document message: {e}")


async def process_vector_message(message: IncomingMessage):
    """处理向量化队列消息"""
    async with message.process():
        try:
            body = json.loads(message.body.decode())
            task_id = body.get("task_id")
            payload = body.get("payload", {})
            
            logger.info(f"Received vector task: {task_id}")
            
            await vector_worker.process_vector_embed(task_id, payload)
            
        except Exception as e:
            logger.error(f"Error processing vector message: {e}")


async def process_kg_message(message: IncomingMessage):
    """处理知识图谱队列消息"""
    async with message.process():
        try:
            body = json.loads(message.body.decode())
            task_id = body.get("task_id")
            payload = body.get("payload", {})
            
            logger.info(f"Received KG task: {task_id}")
            
            await knowledge_graph_worker.process_knowledge_graph(task_id, payload)
            
        except Exception as e:
            logger.error(f"Error processing KG message: {e}")


async def start_workers():
    """启动所有Worker"""
    logger.info("Starting message queue workers...")
    
    # 启动文档处理Worker
    asyncio.create_task(
        rabbitmq_manager.consume_messages(
            settings.QUEUE_DOCUMENT_PROCESS,
            process_document_message
        )
    )
    
    # 启动向量化Worker
    asyncio.create_task(
        rabbitmq_manager.consume_messages(
            settings.QUEUE_VECTOR_EMBED,
            process_vector_message
        )
    )
    
    # 启动知识图谱Worker
    asyncio.create_task(
        rabbitmq_manager.consume_messages(
            settings.QUEUE_KNOWLEDGE_GRAPH,
            process_kg_message
        )
    )
    
    logger.info("All workers started successfully")


async def stop_workers():
    """停止所有Worker"""
    logger.info("Stopping workers...")
    document_worker.is_running = False
    vector_worker.is_running = False
    knowledge_graph_worker.is_running = False
    logger.info("All workers stopped")
