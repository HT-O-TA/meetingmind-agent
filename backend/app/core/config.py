from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # ==================== 应用基础配置 ====================
    APP_NAME: str = "MeetingMind"  # 应用名称，用于API文档和日志
    APP_ENV: str = "development"  # 运行环境：development(开发) / production(生产) / test(测试)
    DEBUG: bool = False  # DEBUG模式开关，开启会输出详细SQL日志
    SECRET_KEY: str = "meetingmind-secret-key-change-in-production"  # 密钥，用于JWT签名、密码加密等安全操作
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # JWT访问令牌过期时间（分钟）

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:123456@localhost:5432/meetingmind"  # PostgreSQL数据库连接字符串

    # ==================== CORS跨域配置 ====================
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'  # 允许的前端跨域地址列表（JSON格式）

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"  # 文件上传存储目录
    MAX_FILE_SIZE: int = 52428800  # 单个文件最大大小（字节，50MB）
    MAX_FILE_COUNT: int = 50  # 单次批量上传最大文件数
    ALLOWED_FILE_EXTENSIONS: str = '["txt", "pdf", "docx", "doc", "md", "csv", "xlsx", "xlsm"]'  # 允许上传的文件格式列表（JSON格式）
    
    # ==================== 文本处理配置 ====================
    CHUNK_SIZE: int = 512  # 固定长度切分模式下的切片大小（字符数）
    CHUNK_OVERLAP: int = 64  # 固定长度切分模式下的切片重叠大小（字符数）
    CHUNK_MODE: str = "speaker"  # 切分模式："speaker"（按说话人发言切分）或 "fixed"（固定长度切分）
    SPEAKER_MIN_CHUNK_SIZE: int = 100  # speaker模式下合并短发言的最小字符阈值
    ENABLE_SEMANTIC_CHUNKING: bool = False  # 是否在文档向量化流程中启用语义分块（默认关闭，保持兼容）
    SEMANTIC_CHUNK_STRATEGY: str = "semantic_hybrid"  # 语义分块策略：semantic/semantic_hybrid/paragraph/fixed_size
    SEMANTIC_CHUNK_USE_LLM: bool = False  # 是否允许语义分块器调用LLM；关闭时使用规则化hybrid降级策略
    SEMANTIC_CHUNK_MIN_SIZE: int = 100  # 语义块最小字符/近似token阈值
    SEMANTIC_CHUNK_MAX_SIZE: int = 1000  # 语义块最大字符/近似token阈值
    SEMANTIC_CHUNK_OVERLAP: int = 50  # 语义分块固定切分降级时的重叠大小
    SEMANTIC_CHUNK_BUILD_HIERARCHY: bool = True  # 是否构建父子块层级关系
    SEMANTIC_CHUNK_PRESERVE_STRUCTURE: bool = True  # 是否优先使用标题层级结构分块

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = "INFO"  # 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL
    LOG_DIR: str = "./logs"  # 日志文件存储目录

    # ==================== Redis缓存配置 ====================
    REDIS_URL: str = "redis://localhost:6379/0"  # Redis连接字符串
    CACHE_TTL: int = 300  # 缓存默认过期时间（秒，5分钟）
    CACHE_ENABLED: bool = False  # 是否启用Redis缓存

    # ==================== 向量化配置 ====================
    EMBEDDING_MODEL: str = "BAAI/bge-m3"  # HuggingFace模型标识（用于远程下载）
    EMBEDDING_MODEL_NAME: str = "bge-m3"  # 当前使用的本地模型文件夹名称（不带前缀）
    VECTOR_DIMENSION: int = 1024  # 向量维度（bge-m3为1024维，预留配置，暂未使用）
    EMBEDDING_DEVICE: str = "cuda"  # 向量化计算设备："cpu" 或 "cuda"
    VECTOR_INDEX_DIR: str = "./vector_index"  # 向量索引存储目录（预留配置，暂未使用）
    TOP_K_DEFAULT: int = 5  # 默认返回的检索结果数量
    SIMILARITY_THRESHOLD: float = 0.7  # 相似度阈值，低于此值的结果将被过滤（0.0表示不过滤）
    
    # ==================== 本地模型配置 ====================
    LOCAL_MODELS_ROOT: str = "./model"  # 本地模型根目录，每个模型一个子文件夹
    
    # ==================== LLM配置（OpenAI兼容接口） ====================
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # LLM API基础URL
    LLM_API_KEY: str = ""  # LLM API密钥（从.env文件读取，不要在此处硬编码）
    LLM_MODEL: str = "qwen3.6-plus"  # 默认使用的LLM模型名称
    LLM_TEMPERATURE: float = 0.7  # LLM温度参数，控制输出随机性（0-1）
    LLM_MAX_TOKENS: int = 1000  # LLM生成的最大token数
    LLM_TIMEOUT: int = 20  # LLM API请求超时时间（秒）
    LLM_MAX_CONTEXT_CHARS: int = 5000  # 传入LLM的最大上下文字符数

    # ==================== RAG评估配置 ====================
    EVAL_LLM_MODEL: str = "qwen-turbo"  # 评估专用轻量模型，空字符串则复用 LLM_MODEL
    EVAL_LLM_MAX_TOKENS: int = 300  # 评估时答案不需要太长，节省token
    EVAL_SKIP_LLM: bool = True  # 是否跳过LLM生成，只计算检索指标；日常调参建议设为 True
    EVAL_TOP_K: int = 5  # 评估时的检索返回数量，覆盖 TOP_K_DEFAULT
    
    # ==================== 多路召回与重排序配置 ====================
    BM25_WEIGHT: float = 0.3  # BM25检索权重（与向量检索权重相加应为1.0）
    VECTOR_WEIGHT: float = 0.7  # 向量检索权重
    RERANK_TOP_N: int = 10  # 重排序前候选数量（从多路召回结果中取前N个进行精排）
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"  # 重排序模型名称（bge-reranker-v2-m3 支持中英双语，性能更强）
    RERANKER_LOCAL_PATH: str = "./model/bge-reranker-v2-m3"  # 本地模型路径（如果已下载到本地）
    ENABLE_MULTI_RETRIEVAL: bool = True  # 是否启用多路召回
    ENABLE_BM25: bool = True  # 是否启用BM25检索
    ENABLE_RERANK: bool = True  # 是否启用重排序
    
    # ==================== 多模态服务配置 ====================
    VISION_API_BASE: str = "https://api.openai.com/v1"  # 视觉API基础URL
    VISION_API_KEY: str = ""  # Vision API密钥
    VISION_MODEL: str = "gpt-4o"  # 视觉模型名称
    VISION_MAX_TOKENS: int = 1000  # Vision最大token数
    WHISPER_API_BASE: str = "https://api.openai.com/v1"  # Whisper API基础URL
    WHISPER_API_KEY: str = ""  # Whisper API密钥
    WHISPER_MODEL: str = "whisper-1"  # Whisper模型名称
    ENABLE_MULTIMODAL: bool = True  # 是否启用多模态服务

    # ==================== Agent规划配置 ====================
    ENABLE_TEMPLATE_PLANNING: bool = True  # 是否启用任务模板库（优先匹配模板，失败再用LLM）
    ENABLE_PLAN_VALIDATION: bool = True  # 是否启用规划验证（语法、逻辑、质量检查）
    ENABLE_PLAN_AUTO_FIX: bool = True  # 是否启用计划自动修复
    TEMPLATE_MATCH_THRESHOLD: float = 0.2  # 模板匹配阈值（0-1）
    MAX_TASKS_IN_PLAN: int = 10  # 计划中最大任务数量
    
    # ==================== 知识图谱配置 ====================
    ENABLE_KNOWLEDGE_GRAPH: bool = True  # 是否启用知识图谱增强检索
    KNOWLEDGE_GRAPH_DEPTH: int = 2  # 图谱扩展深度
    KNOWLEDGE_GRAPH_MIN_SCORE: float = 0.3  # 图谱扩展结果的最低分数阈值
    
    @property
    def LOCAL_EMBEDDING_MODEL_PATH(self) -> str:
        """动态计算当前模型的本地路径"""
        return f"{self.LOCAL_MODELS_ROOT}/{self.EMBEDDING_MODEL_NAME}"

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    @property
    def allowed_file_extensions_list(self) -> List[str]:
        return json.loads(self.ALLOWED_FILE_EXTENSIONS)


settings = Settings()
