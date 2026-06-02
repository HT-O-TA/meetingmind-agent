"""批处理优化的向量化服务"""
import asyncio
import time
from typing import List, Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.core.logger import app_logger


@dataclass
class BatchConfig:
    """批处理配置"""
    batch_size: int = 32
    max_concurrent_batches: int = 4
    timeout_per_batch: int = 60
    retry_count: int = 3
    retry_delay: float = 1.0


@dataclass
class BatchJob:
    """批处理任务"""
    job_id: str
    total_items: int
    processed_items: int = 0
    failed_items: int = 0
    status: str = "pending"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_items: List[Dict[str, Any]] = field(default_factory=list)
    result: List[Any] = field(default_factory=list)


class BatchEmbeddingService:
    """支持批处理优化的向量化服务"""
    
    def __init__(self, embedding_service=None, config: BatchConfig = None):
        self._embedding_service = embedding_service
        self._config = config or BatchConfig()
        self._executor = ThreadPoolExecutor(max_workers=self._config.max_concurrent_batches)
        self._active_jobs: Dict[str, BatchJob] = {}
        self._job_counter = 0
    
    def _get_embedding_service(self):
        """获取或创建embedding服务实例"""
        if self._embedding_service is None:
            from app.services.embedding_service import EmbeddingService
            self._embedding_service = EmbeddingService()
        return self._embedding_service
    
    def _generate_job_id(self) -> str:
        """生成任务ID"""
        self._job_counter += 1
        return f"batch_emb_{int(time.time())}_{self._job_counter}"
    
    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False,
        progress_callback: Callable[[int, int], None] = None
    ) -> List[List[float]]:
        """
        同步批量向量化
        
        Args:
            texts: 文本列表
            batch_size: 批大小（覆盖配置）
            show_progress: 是否显示进度
            progress_callback: 进度回调函数
            
        Returns:
            向量列表
        """
        embedding_service = self._get_embedding_service()
        batch_size = batch_size or self._config.batch_size
        results = []
        
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            try:
                batch_results = embedding_service.encode_batch(batch)
                results.extend(batch_results)
                
                if show_progress:
                    progress = int((batch_num / total_batches) * 100)
                    print(f"Progress: {progress}% ({batch_num}/{total_batches})")
                
                if progress_callback:
                    progress_callback(batch_num, total_batches)
            
            except Exception as e:
                app_logger.error(f"Batch encoding failed at batch {batch_num}: {e}")
                # 对失败的批次使用备用方案
                fallback_results = [embedding_service.encode_text(t) for t in batch]
                results.extend(fallback_results)
        
        return results
    
    async def encode_batch_async(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False,
        progress_callback: Callable[[int, int], Awaitable[None]] = None
    ) -> List[List[float]]:
        """
        异步批量向量化
        
        Args:
            texts: 文本列表
            batch_size: 批大小（覆盖配置）
            show_progress: 是否显示进度
            progress_callback: 异步进度回调
            
        Returns:
            向量列表
        """
        embedding_service = self._get_embedding_service()
        batch_size = batch_size or self._config.batch_size
        
        results = [None] * len(texts)
        semaphore = asyncio.Semaphore(self._config.max_concurrent_batches)
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        async def process_batch(batch_texts: List[str], start_idx: int):
            async with semaphore:
                try:
                    loop = asyncio.get_event_loop()
                    batch_results = await loop.run_in_executor(
                        self._executor,
                        lambda: embedding_service.encode_batch(batch_texts)
                    )
                    
                    for j, result in enumerate(batch_results):
                        results[start_idx + j] = result
                    
                    if show_progress or progress_callback:
                        current = sum(1 for r in results if r is not None)
                        if progress_callback:
                            await progress_callback(current, len(texts))
                
                except Exception as e:
                    app_logger.error(f"Async batch encoding failed: {e}")
                    for j, text in enumerate(batch_texts):
                        results[start_idx + j] = embedding_service.encode_text(text)
        
        tasks = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            tasks.append(process_batch(batch_texts, i))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    def encode_batch_with_retry(
        self,
        texts: List[str],
        batch_size: int = None,
        max_retries: int = None
    ) -> tuple[List[List[float]], List[Dict[str, Any]]]:
        """
        带重试的批量向量化
        
        Args:
            texts: 文本列表
            batch_size: 批大小
            max_retries: 最大重试次数
            
        Returns:
            (成功的结果列表, 失败项列表)
        """
        embedding_service = self._get_embedding_service()
        batch_size = batch_size or self._config.batch_size
        max_retries = max_retries or self._config.retry_count
        
        results = [None] * len(texts)
        failed_items: List[Dict[str, Any]] = []
        
        for retry in range(max_retries):
            pending_indices = [i for i, r in enumerate(results) if r is None]
            
            if not pending_indices:
                break
            
            for i in range(0, len(pending_indices), batch_size):
                batch_indices = pending_indices[i:i + batch_size]
                batch_texts = [texts[idx] for idx in batch_indices]
                
                try:
                    batch_results = embedding_service.encode_batch(batch_texts)
                    for j, idx in enumerate(batch_indices):
                        results[idx] = batch_results[j]
                
                except Exception as e:
                    app_logger.warning(f"Retry {retry + 1}: Batch encoding failed: {e}")
                    for j, idx in enumerate(batch_indices):
                        if retry == max_retries - 1:
                            failed_items.append({
                                "index": idx,
                                "text": batch_texts[j][:100],
                                "error": str(e)
                            })
        
        valid_results = [r if r is not None else embedding_service.encode_text(texts[i]) 
                        for i, r in enumerate(results)]
        
        return valid_results, failed_items
    
    async def encode_large_corpus(
        self,
        texts: List[str],
        job_id: str = None,
        on_progress: Callable[[BatchJob], None] = None
    ) -> Dict[str, Any]:
        """
        大规模语料向量化（带任务管理）
        
        Args:
            texts: 文本列表
            job_id: 任务ID（可选，自动生成）
            on_progress: 进度回调
            
        Returns:
            包含结果和统计信息的字典
        """
        job_id = job_id or self._generate_job_id()
        job = BatchJob(
            job_id=job_id,
            total_items=len(texts),
            start_time=datetime.now()
        )
        self._active_jobs[job_id] = job
        
        try:
            results = await self.encode_batch_async(
                texts,
                show_progress=True,
                progress_callback=lambda current, total: self._update_job_progress(
                    job_id, current, total, on_progress
                )
            )
            
            job.result = results
            job.status = "completed"
            job.end_time = datetime.now()
            
            return {
                "job_id": job_id,
                "status": "completed",
                "results": results,
                "statistics": self._get_job_statistics(job)
            }
        
        except Exception as e:
            job.status = "failed"
            job.end_time = datetime.now()
            app_logger.error(f"Large corpus encoding failed: {e}")
            
            return {
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "statistics": self._get_job_statistics(job)
            }
    
    def _update_job_progress(
        self,
        job_id: str,
        processed: int,
        total: int,
        callback: Callable[[BatchJob], None] = None
    ):
        """更新任务进度"""
        job = self._active_jobs.get(job_id)
        if job:
            job.processed_items = processed
            if callback:
                callback(job)
    
    def _get_job_statistics(self, job: BatchJob) -> Dict[str, Any]:
        """获取任务统计信息"""
        duration = 0
        if job.start_time and job.end_time:
            duration = (job.end_time - job.start_time).total_seconds()
        
        return {
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "failed_items": job.failed_items,
            "duration_seconds": duration,
            "items_per_second": job.processed_items / duration if duration > 0 else 0,
            "success_rate": (job.processed_items - job.failed_items) / max(1, job.total_items)
        }
    
    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """获取任务状态"""
        return self._active_jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """取消任务"""
        job = self._active_jobs.get(job_id)
        if job and job.status in ("pending", "running"):
            job.status = "cancelled"
            job.end_time = datetime.now()
            return True
        return False
    
    def cleanup_completed_jobs(self, max_age_seconds: int = 3600):
        """清理已完成的任务"""
        now = datetime.now()
        to_remove = []
        
        for job_id, job in self._active_jobs.items():
            if job.end_time and job.status in ("completed", "failed", "cancelled"):
                age = (now - job.end_time).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(job_id)
        
        for job_id in to_remove:
            del self._active_jobs[job_id]
        
        return len(to_remove)


class StreamingEmbeddingProcessor:
    """流式向量化处理器 - 适用于超大规模数据"""
    
    def __init__(self, batch_service: BatchEmbeddingService = None):
        self._batch_service = batch_service or BatchEmbeddingService()
        self._buffer: List[str] = []
        self._buffer_size = 100
    
    def add(self, text: str) -> Optional[List[List[float]]]:
        """
        添加文本到缓冲区，满则自动处理
        
        Args:
            text: 文本
            
        Returns:
            如果缓冲区满，返回处理结果
        """
        self._buffer.append(text)
        
        if len(self._buffer) >= self._buffer_size:
            return self.flush()
        
        return None
    
    def flush(self) -> List[List[float]]:
        """强制处理缓冲区"""
        if not self._buffer:
            return []
        
        results = self._batch_service.encode_batch(self._buffer)
        self._buffer.clear()
        
        return results
    
    async def add_async(self, text: str) -> Optional[List[List[float]]]:
        """异步添加文本"""
        self._buffer.append(text)
        
        if len(self._buffer) >= self._buffer_size:
            return await self.flush_async()
        
        return None
    
    async def flush_async(self) -> List[List[float]]:
        """异步强制处理缓冲区"""
        if not self._buffer:
            return []
        
        results = await self._batch_service.encode_batch_async(self._buffer)
        self._buffer.clear()
        
        return results
    
    def get_buffer_size(self) -> int:
        """获取当前缓冲区大小"""
        return len(self._buffer)


# 全局批处理服务实例
_batch_embedding_service: Optional[BatchEmbeddingService] = None


def get_batch_embedding_service() -> BatchEmbeddingService:
    """获取批处理向量化服务"""
    global _batch_embedding_service
    if _batch_embedding_service is None:
        _batch_embedding_service = BatchEmbeddingService()
    return _batch_embedding_service
