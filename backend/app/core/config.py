from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # ==================== 应用基础配置 ====================
    APP_NAME: str = "MeetingMind"  # 应用名称，用于API文档和日志
    APP_ENV: str = "development"  # 运行环境：development(开发) / production(生产) / test(测试)
    DEBUG: bool = False  # DEBUG模式开关，开启会输出详细SQL日志
    SECRET_KEY: str = "meetingmind-secret-key-change-in-production"  # 密钥，用于JWT签名、密码加密等安全操作
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # JWT访问令牌过期时间（分钟）

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/meetingmind"  # PostgreSQL数据库连接字符串

    # ==================== CORS跨域配置 ====================
    CORS_ORIGINS: str = '["http://localhost:5173","http://127.0.0.1:5173","http://localhost:3000","http://127.0.0.1:3000"]'  # 允许的前端跨域地址列表（JSON格式）

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"  # 文件上传存储目录
    MAX_FILE_SIZE: int = 52428800  # 单个文件最大大小（字节，50MB）
    MAX_FILE_COUNT: int = 50  # 单次批量上传最大文件数
    ALLOWED_FILE_EXTENSIONS: str = '["txt", "pdf", "docx", "md", "csv", "xlsx", "xlsm"]'  # 只保留能够解析和校验内容结构的文档格式
    
    # ==================== 文本处理配置 ====================
    # 唯一正式策略：说话人感知语义分块；以下是可复现实验的默认参数，不写未冻结效果指标。
    CHUNK_SIZE: int = 300  # 基础切片大小（字符数）
    CHUNK_OVERLAP: int = 30  # 切片重叠大小（字符数）
    SPEAKER_MIN_CHUNK_SIZE: int = 50  # 合并短发言的最小字符阈值
    # 语义分块配置（统一使用 SPEAKER_AWARE_HYBRID）
    SEMANTIC_CHUNK_MIN_SIZE: int = 50  # 语义块最小字符阈值（实验调优后）
    SEMANTIC_CHUNK_MAX_SIZE: int = 300  # 语义块最大字符阈值（实验调优后）
    SEMANTIC_CHUNK_OVERLAP: int = 30  # 语义块重叠大小（实验调优后）
    SEMANTIC_CHUNK_THRESHOLD: float = 0.7  # 语义相似度阈值（实验调优后）

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = "INFO"  # 日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL

    # ==================== Redis缓存配置（混合方案） ====================
    REDIS_URL: str = "redis://localhost:6379/0"  # Redis连接字符串
    CACHE_TTL: int = 300  # 缓存默认过期时间（秒，5分钟）
    CACHE_ENABLED: bool = True  # 是否启用Redis缓存

    # Agent 运行检查点：只保存可恢复的任务状态，不是长期知识记忆
    AGENT_CHECKPOINT_ENABLED: bool = True
    AGENT_CHECKPOINT_BACKEND: str = "file"  # file（开发/单进程）或 postgres（生产/多进程）
    AGENT_CHECKPOINT_PATH: str = "./data/agent_checkpoints.pkl"
    AGENT_CHECKPOINT_POSTGRES_URL: str = "postgresql://postgres:password@localhost:5432/meetingmind"
    AGENT_CHECKPOINT_MAX_BYTES: int = 2_000_000
    AGENT_CHECKPOINT_RETENTION_SECONDS: int = 86_400
    AGENT_CHECKPOINT_CLAIM_LEASE_SECONDS: int = 600
    
    # LLM 缓存配置（原生Redis实现）
    LLM_CACHE_TTL: int = 3600  # LLM 缓存过期时间（秒，1小时）

    # ==================== RabbitMQ消息队列配置 ====================
    RABBITMQ_URL: str = "amqp://admin:admin123@localhost:5672"  # RabbitMQ连接字符串
    RABBITMQ_MAX_RETRIES: int = 3  # 最大重试次数
    RABBITMQ_RETRY_DELAY: int = 5  # 重试延迟（秒）
    RABBITMQ_CONNECT_TIMEOUT_SECONDS: float = 10.0
    RABBITMQ_PUBLISH_TIMEOUT_SECONDS: float = 10.0
    
    # 任务队列配置
    QUEUE_DOCUMENT_PROCESS: str = "document_process"  # 文档处理队列
    QUEUE_VECTOR_EMBED: str = "vector_embed"  # 向量化队列
    QUEUE_AUDIO_TRANSCRIBE: str = "audio_transcribe"  # 本地 ASR 转写队列
    QUEUE_MEMORY_INDEX: str = "memory_index"  # 长期记忆索引同步队列
    MEMORY_OUTBOX_BATCH_SIZE: int = 50
    MEMORY_OUTBOX_PUBLISH_INTERVAL_SECONDS: float = 2.0
    MEMORY_OUTBOX_CLAIM_LEASE_SECONDS: int = 60
    MEMORY_INDEX_WORKER_ENABLED: bool = False
    QUEUE_TASK_TIMEOUT: int = 3600  # 任务默认超时时间（秒）
    QUEUE_PREFETCH_COUNT: int = 1  # 消费者预取消息数量
    QUEUE_MAX_RETRIES: int = 2  # 消费失败后的额外投递次数；总尝试数=3
    QUEUE_RETRY_DELAY_SECONDS: int = 5  # 固定延迟重试队列 TTL
    QUEUE_MAX_LENGTH: int = 10000  # 满队列拒绝新发布并由 publisher confirm 暴露错误
    QUEUE_DLX_NAME: str = "meetingmind.dlx"
    QUEUE_TASK_RETENTION_SECONDS: int = 86400  # Redis 中终态/查询状态保留 24 小时
    QUEUE_CLAIM_TTL_SECONDS: int = 3660  # 略长于单任务超时，防止并发重复消费

    # ==================== 向量化配置 ====================
    EMBEDDING_MODEL: str = "BAAI/bge-m3"  # HuggingFace模型标识（用于远程下载）
    EMBEDDING_MODEL_NAME: str = "bge-m3"  # 当前使用的本地模型文件夹名称（不带前缀）
    EMBEDDING_DEVICE: str = "cpu"  # 默认 CPU；本地模型环境可显式改为 cuda
    TOP_K_DEFAULT: int = 5  # 默认返回的检索结果数量
    SIMILARITY_THRESHOLD: float = 0.7  # 相似度阈值，低于此值的结果将被过滤（0.0表示不过滤）
    
    # ==================== 本地模型配置 ====================
    LOCAL_MODELS_ROOT: str = "../model"  # 项目根目录下的本地模型目录
    LOCAL_MODEL_ONLY: bool = True  # 禁止运行时从 HuggingFace 等模型源下载
    COMPLEXITY_MODEL_NAME: str = "Qwen3-1.7B"  # 复杂度分类器使用的本地模型名称
    
    # ==================== LLM配置（OpenAI兼容接口） ====================
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # LLM API基础URL
    LLM_API_KEY: str = ""  # LLM API密钥（从.env文件读取，不要在此处硬编码）
    LLM_MODEL: str = "qwen3.6-plus"  # 默认使用的LLM模型名称
    LLM_TEMPERATURE: float = 0.7  # LLM温度参数，控制输出随机性（0-1）
    LLM_MAX_TOKENS: int = 1000  # LLM生成的最大token数
    PLAN_LLM_MAX_TOKENS: int = 3000  # 规划阶段专用最大token数（JSON结构较大，需要更多token防止截断）
    LLM_TIMEOUT: int = 120  # LLM API请求超时时间（秒）
    LLM_MAX_CONTEXT_CHARS: int = 5000  # 传入LLM的最大上下文字符数
    # TokenBudgetLedger 的保守初值；模型供应商调整窗口后由环境变量显式覆盖。
    LLM_CONTEXT_WINDOW_TOKENS: int = 32768
    LLM_MODEL_CONTEXT_WINDOWS: str = "{}"  # JSON: {"model-name": context_window_tokens}
    LLM_RUN_TOKEN_BUDGET: int = 65536  # 单次 Agent Run 的输入+最大输出累计预算
    LLM_NODE_TOKEN_BUDGET: int = 32768  # 单节点在重试/多任务中的累计预算
    LLM_MAX_CALLS_PER_RUN: int = 16
    LLM_TOKEN_SAFETY_MARGIN_RATIO: float = 0.15
    CONTEXT_MAX_ITEM_CHARS: int = 1600  # 单条证据上限，避免一个长结果吞掉全部预算
    CONTEXT_MAX_ITEMS: int = 8
    CONTEXT_MAX_CHUNKS_PER_DOCUMENT: int = 3  # 为不同文档/来源保留多样性
    CONTEXT_ANCHOR_MAX_CHARS: int = 700
    MODEL_TURBO_NAME: str = "qwen-turbo"
    MODEL_PLUS_NAME: str = "qwen3.6-plus"
    MODEL_MAX_NAME: str = "qwen-max"

    QUALITY_GATE_MODEL: str = "qwen-turbo"  # Agent 结果质量门禁模型
    
    # ==================== 多路召回与重排序配置 ====================
    BM25_WEIGHT: float = 0.3  # BM25检索权重（与向量检索权重相加应为1.0）
    VECTOR_WEIGHT: float = 0.7  # 向量检索权重
    RERANK_TOP_N: int = 10  # 重排序前候选数量（从多路召回结果中取前N个进行精排）
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"  # 重排序模型名称（bge-reranker-v2-m3 支持中英双语，性能更强）
    RERANKER_LOCAL_PATH: str = "../model/bge-reranker-v2-m3"  # 本地模型路径
    ENABLE_RERANK: bool = True  # 是否启用重排序

    # ==================== Milvus向量数据库配置 ====================
    MILVUS_URI: str = "http://localhost:19530"  # Milvus连接URI，Docker部署使用"http://localhost:19530"
    MILVUS_TOKEN: str = ""  # Milvus认证令牌（Zilliz Cloud时需要）
    VECTOR_COLLECTION_NAME: str = "meetingmind_docs"  # 向量集合名称（供 MilvusVectorStore 使用）
    USE_GPU: bool = False
    USE_FP16: bool = False
    BGE_M3_MODEL_PATH: str = "./model/bge-m3"
    
    # ==================== 本地 ASR 配置 ====================
    # 可选重型能力：普通 Web/Worker 冷启动不导入 torch/FunASR，仅消费音频任务时懒加载。
    ENABLE_ASR: bool = False
    ASR_PROVIDER: str = "funasr"
    ASR_MODEL: str = "paraformer-zh"
    ASR_VAD_MODEL: str = "fsmn-vad"
    ASR_PUNC_MODEL: str = "ct-punc"
    ASR_SPK_MODEL: str = "cam++"
    ASR_DEVICE: str = "auto"  # auto/cpu/cuda/cuda:0
    ASR_HUB: str = "ms"
    ASR_BATCH_SIZE_S: int = 300
    ASR_MAX_AUDIO_SIZE_BYTES: int = 209715200  # 200 MiB
    ASR_MAX_DURATION_SECONDS: int = 14400  # 4 小时
    ASR_DELETE_UPLOAD_AFTER_SUCCESS: bool = True
    ASR_ALLOWED_EXTENSIONS: str = "wav"

    # ==================== 安全护栏配置 ====================
    INJECTION_GUARD_DEPTH: str = "light"  # light/heavy 检测深度

    # ==================== 并行执行配置 ====================
    MAX_PARALLEL_WORKERS: int = 3  # 最大并行工作线程数
    TASK_TIMEOUT_SECONDS: int = 60  # 单任务超时时间（秒）

    # ==================== 规划 Token 预算保护配置 ====================
    PLAN_MAX_TASKS: int = 8  # 规划最大任务数（动态调整）
    PLAN_MIN_TOKENS: int = 500  # 规划最小可用 token
    PLAN_COMPLEXITY_THRESHOLD: float = 0.7  # 触发渐进式规划的复杂度阈值
    # 路由阈值当前是保守初始值，必须由 route_eval 数据集重新标定后再写入报告。
    ROUTE_TASK_CONFIDENCE_THRESHOLD: float = 0.65
    ROUTE_COMPLEXITY_CONFIDENCE_THRESHOLD: float = 0.65

    # ==================== 统一质量门禁配置 ====================
    QUALITY_GATE_REPLAN_THRESHOLD: float = 0.5  # 触发重规划的分数阈值
    QUALITY_GATE_POLISH_THRESHOLD: float = 0.7  # 触发抛光的分数阈值

    # ==================== HITL 细粒度风险控制配置 ====================
    HITL_MIN_RISK_LEVEL: str = "HIGH"  # 触发人工确认的最低风险等级（LOW/MEDIUM/HIGH/CRITICAL）
    HITL_AUTO_APPROVE_LOW: bool = True  # LOW 风险自动放行（不弹确认）
    HITL_AUTO_APPROVE_MEDIUM: bool = True  # MEDIUM 风险自动放行（不弹确认）

    # Jira Cloud REST v3 配置
    JIRA_ENABLED: bool = False  # 仅凭据齐全并计划真实调用时开启
    JIRA_URL: str = ""  # 站点地址，例如 https://example.atlassian.net
    JIRA_USERNAME: str = ""  # Atlassian 账号邮箱
    JIRA_API_TOKEN: str = ""  # Atlassian API Token，禁止提交到 Git
    JIRA_HTTP_TIMEOUT_SECONDS: float = 15.0
    JIRA_MAX_RETRIES: int = 2  # 仅用于 GET/PUT 等幂等请求
    JIRA_MAX_RETRY_DELAY_SECONDS: float = 10.0

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.AGENT_CHECKPOINT_BACKEND.lower() not in {"file", "postgres"}:
            raise ValueError("AGENT_CHECKPOINT_BACKEND 只能是 file 或 postgres")
        if min(
            self.AGENT_CHECKPOINT_MAX_BYTES,
            self.AGENT_CHECKPOINT_RETENTION_SECONDS,
            self.AGENT_CHECKPOINT_CLAIM_LEASE_SECONDS,
        ) <= 0:
            raise ValueError("Agent checkpoint 大小、保留时间和租约必须大于 0")
        if self.LLM_CONTEXT_WINDOW_TOKENS <= 0:
            raise ValueError("LLM_CONTEXT_WINDOW_TOKENS 必须大于 0")
        if self.LLM_RUN_TOKEN_BUDGET <= 0 or self.LLM_NODE_TOKEN_BUDGET <= 0:
            raise ValueError("LLM Token 运行/节点预算必须大于 0")
        if self.LLM_MAX_CALLS_PER_RUN <= 0:
            raise ValueError("LLM_MAX_CALLS_PER_RUN 必须大于 0")
        if not 0 <= self.LLM_TOKEN_SAFETY_MARGIN_RATIO < 1:
            raise ValueError("LLM_TOKEN_SAFETY_MARGIN_RATIO 必须位于 [0, 1)")
        if min(
            self.CONTEXT_MAX_ITEM_CHARS,
            self.CONTEXT_MAX_ITEMS,
            self.CONTEXT_MAX_CHUNKS_PER_DOCUMENT,
            self.CONTEXT_ANCHOR_MAX_CHARS,
        ) <= 0:
            raise ValueError("上下文组装数量与字符预算必须大于 0")
        try:
            windows = json.loads(self.LLM_MODEL_CONTEXT_WINDOWS)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM_MODEL_CONTEXT_WINDOWS 必须是 JSON 对象") from exc
        if not isinstance(windows, dict) or any(
            not str(model).strip() or isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0
            for model, tokens in windows.items()
        ):
            raise ValueError("LLM_MODEL_CONTEXT_WINDOWS 必须映射模型名到正整数")
        if self.APP_ENV.lower() == "production":
            insecure = {
                "meetingmind-secret-key-change-in-production",
                "meetingmind-dev-only-secret-change-before-production",
                "your-secret-key-here-change-in-production",
            }
            if self.SECRET_KEY in insecure or len(self.SECRET_KEY) < 32:
                raise ValueError("生产环境 SECRET_KEY 必须是至少 32 字符的非示例值")
            if self.DEBUG:
                raise ValueError("生产环境禁止开启 DEBUG")
            if "*" in self.cors_origins_list:
                raise ValueError("生产环境 CORS_ORIGINS 禁止通配符")
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins_list):
                raise ValueError("生产环境 CORS_ORIGINS 禁止本机开发地址")
        return self
    
    def _get_backend_dir(self) -> str:
        """获取 backend 目录的绝对路径"""
        import os
        # config.py 在 app/core/ 下，所以需要向上2级
        backend_dir = os.path.dirname(os.path.abspath(__file__))  # core
        backend_dir = os.path.dirname(backend_dir)  # app
        backend_dir = os.path.dirname(backend_dir)  # backend
        return backend_dir
    
    @property
    def LOCAL_EMBEDDING_MODEL_PATH(self) -> str:
        """动态计算当前嵌入模型的本地路径（使用绝对路径）"""
        import os
        backend_dir = self._get_backend_dir()
        # 拼接本地模型根目录（支持相对路径和绝对路径）
        base_path = os.path.join(backend_dir, self.LOCAL_MODELS_ROOT)
        base_path = os.path.normpath(base_path)
        return os.path.join(base_path, self.EMBEDDING_MODEL_NAME)
    
    @property
    def COMPLEXITY_MODEL_PATH(self) -> str:
        """动态计算复杂度分类器模型的本地路径（使用绝对路径）"""
        import os
        backend_dir = self._get_backend_dir()
        base_path = os.path.join(backend_dir, self.LOCAL_MODELS_ROOT)
        base_path = os.path.normpath(base_path)
        return os.path.join(base_path, self.COMPLEXITY_MODEL_NAME)
    
    @property
    def RERANKER_MODEL_PATH(self) -> str:
        """动态计算重排序模型的本地路径（使用绝对路径）"""
        import os
        backend_dir = self._get_backend_dir()
        # 如果是相对路径，转换为绝对路径
        reranker_path = self.RERANKER_LOCAL_PATH
        if not os.path.isabs(reranker_path):
            reranker_path = os.path.join(backend_dir, reranker_path)
            reranker_path = os.path.normpath(reranker_path)
        return reranker_path
    
    @property
    def UPLOAD_DIR_ABSOLUTE(self) -> str:
        """获取上传目录的绝对路径"""
        import os
        backend_dir = self._get_backend_dir()
        # 如果是相对路径，转换为绝对路径
        upload_dir = self.UPLOAD_DIR
        if not os.path.isabs(upload_dir):
            upload_dir = os.path.join(backend_dir, upload_dir)
            upload_dir = os.path.normpath(upload_dir)
        return upload_dir
    
    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    @property
    def allowed_file_extensions_list(self) -> List[str]:
        return json.loads(self.ALLOWED_FILE_EXTENSIONS)

    @property
    def llm_model_context_windows(self) -> dict[str, int]:
        return {
            str(model): int(tokens)
            for model, tokens in json.loads(self.LLM_MODEL_CONTEXT_WINDOWS).items()
        }


settings = Settings()
