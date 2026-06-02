"""重排序器 - 使用 BGE-Reranker 模型"""
import asyncio
from typing import List, Dict, Any, Optional
from app.core.logger import app_logger
from app.core.config import settings

class Reranker:
    """
    重排序器 - 使用 BGE-Reranker 模型
    
    BGE-Reranker 是一个基于交叉编码器的重排序模型，
    用于对检索结果进行精排，提升检索精度。
    """
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = None
        self._load_model()
    
    def _load_model(self):
        """加载 BGE-Reranker 模型"""
        try:
            from FlagEmbedding import FlagReranker
            import torch
            import os
            
            # 检查是否有GPU
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            app_logger.info(f"[Reranker] 使用设备: {self.device}")
            
            # 确定模型路径
            local_path = settings.RERANKER_LOCAL_PATH
            model_name = settings.RERANKER_MODEL_NAME
            
            # 优先使用本地模型
            if os.path.exists(local_path):
                app_logger.info(f"[Reranker] 使用本地模型: {local_path}")
                self.model = FlagReranker(local_path, use_fp16=True)
            else:
                app_logger.info(f"[Reranker] 使用HuggingFace模型: {model_name}")
                self.model = FlagReranker(model_name, use_fp16=True)
            
            app_logger.info(f"[Reranker] 成功加载模型: {local_path if os.path.exists(local_path) else model_name}")
        except ImportError as e:
            app_logger.warning(f"[Reranker] 未安装 FlagEmbedding，将使用简单重排序: {e}")
            self.model = None
        except Exception as e:
            app_logger.error(f"[Reranker] 加载模型失败: {e}")
            self.model = None
    
    def _simple_rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        简单重排序（当无法加载BGE-Reranker时使用）
        
        使用词重叠度和位置权重进行简单排序
        """
        query_lower = query.lower()
        results = []
        
        for doc in documents:
            content = doc.get('content', '')
            content_lower = content.lower()
            
            # 计算词重叠度
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            overlap = len(query_words.intersection(content_words))
            
            # 计算位置分数（关键词出现在前面更好）
            position_score = 0.0
            for word in query_words:
                idx = content_lower.find(word)
                if idx != -1:
                    position_score += 1.0 / (idx + 1)
            
            # 综合分数
            score = overlap + position_score * 0.1
            
            results.append({
                **doc,
                'rerank_score': score
            })
        
        # 按分数降序排序
        results.sort(key=lambda x: x.get('rerank_score', 0) + x.get('score', 0), reverse=True)
        
        return results
    
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """
        对文档进行重排序
        
        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 返回前n个结果
            
        Returns:
            重排序后的文档列表
        """
        if not documents:
            return []
        
        # 如果没有加载BGE-Reranker，使用简单重排序
        if self.model is None:
            return self._simple_rerank(query, documents)[:top_n]
        
        try:
            # 准备输入数据
            pairs = [[query, doc.get('content', '')] for doc in documents]
            
            # 调用模型进行重排序
            scores = self.model.compute_score(pairs)
            
            # 添加重排序分数
            results = []
            for doc, score in zip(documents, scores):
                results.append({
                    **doc,
                    'rerank_score': float(score)
                })
            
            # 按重排序分数降序排序
            results.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
            
            app_logger.debug(f"[Reranker] 重排序完成，输入 {len(documents)} 个文档，输出 {top_n} 个")
            
            return results[:top_n]
        
        except Exception as e:
            app_logger.error(f"[Reranker] 重排序失败: {e}")
            # 降级到简单重排序
            return self._simple_rerank(query, documents)[:top_n]
    
    async def arerank(self, query: str, documents: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """
        异步版本的重排序
        
        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 返回前n个结果
            
        Returns:
            重排序后的文档列表
        """
        # 在单独的线程中执行重排序，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.rerank,
            query,
            documents,
            top_n
        )


# 全局重排序器实例
_reranker = None

def get_reranker() -> Reranker:
    """获取全局重排序器实例"""
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
