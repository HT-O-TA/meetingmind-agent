"""文本向量化服务"""
from typing import List, Optional
import os
import json
import numpy as np
import jieba
from app.core.config import settings
from app.core.logger import app_logger


class EmbeddingService:
    """基于Sentence-BERT的文本向量化服务"""
    
    _model_cache = {}  # 改为字典，key为模型名称，value为模型实例
    _fallback_cache = None
    
    def __init__(self):
        self.model = None
        self.use_fallback = False
        self._load_model()
    
    def _load_model(self):
        """加载向量化模型（优先使用本地模型）"""
        model_name = settings.EMBEDDING_MODEL_NAME
        local_model_path = settings.LOCAL_EMBEDDING_MODEL_PATH

        app_logger.debug(f"Model name: {model_name}")
        app_logger.debug(f"Local model path: {local_model_path}")
        app_logger.debug(f"Path exists: {os.path.exists(local_model_path)}")
        
        # 检查本地模型目录是否存在且包含模型文件
        has_local_model = False
        if os.path.exists(local_model_path):
            # 检查是否包含Sentence-BERT模型的必要文件
            # 不同模型可能使用不同的tokenizer：BERT使用vocab.txt，SentencePiece使用sentencepiece.bpe.model
            # 模型权重可能是 pytorch_model.bin 或 model.safetensors
            has_config = os.path.exists(os.path.join(local_model_path, 'config.json'))
            has_tokenizer_config = os.path.exists(os.path.join(local_model_path, 'tokenizer.json'))
            has_weights = os.path.exists(os.path.join(local_model_path, 'pytorch_model.bin')) or \
                        os.path.exists(os.path.join(local_model_path, 'model.safetensors'))
            has_tokenizer = os.path.exists(os.path.join(local_model_path, 'vocab.txt')) or \
                        os.path.exists(os.path.join(local_model_path, 'sentencepiece.bpe.model'))
            has_local_model = has_config and has_tokenizer_config and has_weights and has_tokenizer
            
            app_logger.debug(f"[DEBUG] Has config: {has_config}")
            app_logger.debug(f"[DEBUG] Has tokenizer config: {has_tokenizer_config}")
            app_logger.debug(f"[DEBUG] Has weights: {has_weights}")
            app_logger.debug(f"[DEBUG] Has tokenizer: {has_tokenizer}")
            app_logger.debug(f"[DEBUG] Has local model: {has_local_model}")
        
        if has_local_model:
            try:
                if model_name not in EmbeddingService._model_cache:
                    app_logger.info(f"Loading local embedding model from: {local_model_path}")
                    from sentence_transformers import SentenceTransformer
                    EmbeddingService._model_cache[model_name] = SentenceTransformer(
                        local_model_path,
                        device=settings.EMBEDDING_DEVICE,
                        local_files_only=True,
                    )
                    app_logger.info(f"Local embedding model '{model_name}' loaded successfully")
                self.model = EmbeddingService._model_cache[model_name]
                self.use_fallback = False
                app_logger.debug(f"[DEBUG] Model loaded successfully, use_fallback: {self.use_fallback}")
                return
            except Exception as e:
                app_logger.warning(f"Failed to load local model '{model_name}': {e}")
                app_logger.debug(f"[DEBUG] Exception details: {type(e).__name__}: {e}")
                # 本地模型存在但加载失败（如CUDA不可用），直接降级到fallback，不尝试远程下载
                app_logger.info("Local model load failed, skipping remote download, falling back to word frequency embedding")
                self.use_fallback = True
                self._init_fallback()
                return

        # 本地模型缺失时只使用确定性的本地词频向量，绝不访问模型源。
        if not os.path.exists(local_model_path):
            app_logger.warning(
                "Local embedding model is missing; remote model downloads are disabled. "
                "Using the deterministic fallback embedding."
            )

        app_logger.info("Falling back to simple word frequency based embedding")
        self.use_fallback = True
        self._init_fallback()
    
    def _init_fallback(self):
        """初始化备用向量化方案"""
        self.fallback_dimension = 100
        self.fallback_vocab = {}
        self.fallback_idf = {}
        
        common_words = [
            '会议', '讨论', '项目', '工作', '问题', '计划', '方案', '建议',
            '需要', '负责', '完成', '时间', '任务', '目标', '进度', '团队',
            '开发', '设计', '测试', '部署', '文档', '报告', '分析', '评估',
            '会议讨论', '项目计划', '工作任务', '问题分析', '方案设计', '时间安排',
            '任务分配', '目标设定', '进度跟踪', '团队协作', '开发进度', '设计方案',
            '测试报告', '部署计划', '文档编写', '报告撰写', '分析报告', '评估结果',
            '讨论内容', '项目进展', '工作计划', '问题解决', '方案实施', '任务完成',
            '目标达成', '团队管理', '开发工作', '设计评审', '测试用例', '部署方案',
            '文档管理', '会议记录', '分析数据', '评估标准', '讨论决定', '项目管理',
            '工作总结', '问题反馈', '方案优化', '时间管理', '任务管理', '目标管理',
            '进度管理', '团队建设', '开发环境', '设计规范', '测试环境', '部署流程',
            '文档规范', '报告格式', '分析方法', '评估指标', '讨论要点', '项目目标',
            '工作流程', '问题排查', '方案论证', '时间节点', '任务优先级', '目标分解'
        ]
        for idx, word in enumerate(common_words[:self.fallback_dimension]):
            self.fallback_vocab[word] = idx
    
    def _fallback_encode(self, text: str) -> List[float]:
        """
        基于词频的简单向量化（备用方案）
        
        Args:
            text: 输入文本
            
        Returns:
            向量表示（浮点数列表）
        """
        if not text or not isinstance(text, str):
            return [0.0] * self.fallback_dimension
        
        # 使用 jieba 分词
        words = jieba.lcut(text)
        
        embedding = [0.0] * self.fallback_dimension
        match_count = 0
        
        # 检查每个词是否在词汇表中
        for word in words:
            if word in self.fallback_vocab:
                idx = self.fallback_vocab[word]
                embedding[idx] += 1.0
                match_count += 1
        
        # 归一化
        if match_count > 0:
            embedding = [val / match_count for val in embedding]
        
        return embedding
    
    def encode_text(self, text: str) -> List[float]:
        """
        单文本向量化
        
        Args:
            text: 输入文本
            
        Returns:
            向量表示（浮点数列表）
        """
        if not text or not isinstance(text, str):
            return []
        
        if self.use_fallback:
            return self._fallback_encode(text)
        
        try:
            embedding = self.model.encode(text)
            return embedding.tolist()
        except Exception as e:
            app_logger.error(f"Failed to encode text: {e}")
            return self._fallback_encode(text)
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本向量化
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts or not isinstance(texts, list):
            return []
        
        if self.use_fallback:
            return [self._fallback_encode(text) for text in texts]

        try:
            embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as e:
            app_logger.error(f"Failed to encode batch texts: {e}")
            return [self._fallback_encode(text) for text in texts]

    async def embed_chunk(self, chunk_id: int) -> None:
        """为数据库中的单个文档块重新生成向量。

        这是 RabbitMQ ``vector_embed`` Worker 的正式执行入口；找不到块时
        明确失败，避免任务被误报为成功。
        """
        from app.db.database import AsyncSessionLocal
        from app.models.vector import VectorChunk
        from sqlalchemy import select, update

        async with AsyncSessionLocal() as db:
            # 只读取文本和软删除标记，避免 asyncpg 尝试解码
            # embedding_array 的 pgvector 自定义类型。
            row = (
                await db.execute(
                    select(VectorChunk.chunk_text, VectorChunk.deleted_at)
                    .where(VectorChunk.id == int(chunk_id))
                )
            ).one_or_none()
            if row is None or row.deleted_at is not None:
                raise LookupError(f"Vector chunk not found: {chunk_id}")
            embedding = self.encode_text(row.chunk_text)
            if not embedding:
                raise ValueError(f"Vector chunk is empty: {chunk_id}")
            await db.execute(
                update(VectorChunk)
                .where(VectorChunk.id == int(chunk_id))
                .values(
                    embedding=json.dumps(embedding),
                    embedding_array=embedding,
                    embedding_model=(
                "fallback-word-frequency-v1"
                if self.use_fallback
                else settings.EMBEDDING_MODEL_NAME
                    ),
                )
            )
            await db.commit()
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            相似度分数（0-1）
        """
        if not vec1 or not vec2:
            return 0.0
        
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
        except Exception as e:
            app_logger.error(f"Failed to calculate similarity: {e}")
            return 0.0
    
    def get_vector_dimension(self) -> int:
        """获取向量维度"""
        if self.use_fallback:
            return self.fallback_dimension
        
        if not self.model:
            return 0
        
        try:
            return self.model.get_sentence_embedding_dimension()
        except Exception:
            return 384  # 默认维度
    
    def get_status(self) -> dict:
        """获取服务状态"""
        model_info = settings.EMBEDDING_MODEL
        if not self.use_fallback:
            if self._is_local_model():
                model_info = f"local://{settings.LOCAL_EMBEDDING_MODEL_PATH}"
        
        return {
            "status": "online",
            "model": model_info if not self.use_fallback else "fallback (word frequency)",
            "dimension": self.get_vector_dimension(),
            "device": settings.EMBEDDING_DEVICE if not self.use_fallback else "CPU",
            "fallback_mode": self.use_fallback,
            "local_model_used": not self.use_fallback and self._is_local_model()
        }
    
    def _is_local_model(self) -> bool:
        """检查是否使用本地模型"""
        return hasattr(self, 'model') and self.model is not None and \
            os.path.exists(settings.LOCAL_EMBEDDING_MODEL_PATH)
