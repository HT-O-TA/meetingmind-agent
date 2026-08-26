from pydantic import model_validator
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
    CORS_ORIGINS: str = '["http://localhost:5173","http://127.0.0.1:5173","http://localhost:3000","http://127.0.0.1:3000"]'  # 允许的前端跨域地址列表（JSON格式）

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"  # 文件上传存储目录
    MAX_FILE_SIZE: int = 52428800  # 单个文件最大大小（字节，50MB）
    MAX_FILE_COUNT: int = 50  # 单次批量上传最大文件数
    ALLOWED_FILE_EXTENSIONS: str = '["txt", "pdf", "docx", "doc", "md", "csv", "xlsx", "xlsm"]'  # 允许上传的文件格式列表（JSON格式）
    
    # ==================== 文本处理配置 ====================
    # SPEAKER_AWARE_HYBRID 参数调优实验结论（基于会议文档数据集）：
    # 最佳配置: min=50, max=300, overlap=30, threshold=0.7, MRR=0.517
    # 策略: 说话人感知+语义连贯性混合分块，无说话人信息时回退为纯语义分块
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
    
    # LLM 缓存配置（原生Redis实现）
    LLM_CACHE_TTL: int = 3600  # LLM 缓存过期时间（秒，1小时）

    # ==================== 记忆系统 TTL 四层体系 ====================
    # 记忆系统 TTL 配置
    # 注意：以下 TTL 仅为 Redis 缓存过期时间，PostgreSQL 主存储中的数据不会因缓存过期而丢失
    # 
    # 四层记忆架构：
    # 层1：WorkingMemory（AgentState 内存）—— 无TTL，随请求生命周期
    # 层2：SessionMemory（Redis）—— 会话级短期记忆
    MEMORY_SESSION_TTL: int = 21600          # 会话记忆缓存过期时间（秒，6小时）
    # 层3：MeetingMemory（PostgreSQL + Milvus）—— 跨会议长期记忆
    MEMORY_MEETING_TTL_DAYS: int = 730       # 会议记忆保留天数（2年），0=永不过期
    MEMORY_LONG_TERM_DEFAULT_DAYS: int = 365  # 长期记忆默认有效期（天），0=永不过期
    # 层4：KnowledgeGraph（Neo4j）—— 永久存储，无TTL
    #
    # Redis 热缓存（层3的热点数据缓存，失效后自动从 PG 重建）
    MEMORY_HOT_CACHE_TTL: int = 3600         # 热点记忆Redis缓存过期（秒，1小时）
    MEMORY_INDEX_TTL: int = 86400            # 记忆ID索引缓存过期（秒，24小时）
    MEMORY_CONTEXT_TTL: int = 604800         # 会议上下文缓存过期（秒，7天）
    MEMORY_COMPRESS_MAX_CHARS: int = 300     # Level-1 摘要压缩目标字符数
    
    # FastAPI-Cache 配置
    ENABLE_API_CACHE: bool = True  # 是否启用 API 响应缓存
    API_CACHE_TTL: int = 60  # API 缓存默认过期时间（秒，1分钟）

    # ==================== RabbitMQ消息队列配置 ====================
    RABBITMQ_URL: str = "amqp://admin:admin123@localhost:5672"  # RabbitMQ连接字符串
    RABBITMQ_POOL_SIZE: int = 10  # RabbitMQ连接池大小
    RABBITMQ_MAX_RETRIES: int = 3  # 最大重试次数
    RABBITMQ_RETRY_DELAY: int = 5  # 重试延迟（秒）
    RABBITMQ_CONNECT_TIMEOUT_SECONDS: float = 10.0
    RABBITMQ_PUBLISH_TIMEOUT_SECONDS: float = 10.0
    
    # 任务队列配置
    QUEUE_DOCUMENT_PROCESS: str = "document_process"  # 文档处理队列
    QUEUE_VECTOR_EMBED: str = "vector_embed"  # 向量化队列
    QUEUE_KNOWLEDGE_GRAPH: str = "knowledge_graph"  # 知识图谱构建队列
    QUEUE_AGENT_EXECUTE: str = "agent_execute"  # Agent执行队列
    QUEUE_AUDIO_TRANSCRIBE: str = "audio_transcribe"  # 本地 ASR 转写队列
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
    EMBEDDING_DEVICE: str = "cuda"  # 向量化计算设备："cpu" 或 "cuda"
    TOP_K_DEFAULT: int = 5  # 默认返回的检索结果数量
    SIMILARITY_THRESHOLD: float = 0.7  # 相似度阈值，低于此值的结果将被过滤（0.0表示不过滤）
    
    # ==================== 本地模型配置 ====================
    LOCAL_MODELS_ROOT: str = "./model"  # 本地模型根目录，每个模型一个子文件夹
    COMPLEXITY_MODEL_NAME: str = "qwen3-0.6B"  # 复杂度分类器使用的本地模型名称
    
    # ==================== LLM配置（OpenAI兼容接口） ====================
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # LLM API基础URL
    LLM_API_KEY: str = ""  # LLM API密钥（从.env文件读取，不要在此处硬编码）
    LLM_MODEL: str = "qwen3.6-plus"  # 默认使用的LLM模型名称
    LLM_TEMPERATURE: float = 0.7  # LLM温度参数，控制输出随机性（0-1）
    LLM_MAX_TOKENS: int = 1000  # LLM生成的最大token数
    PLAN_LLM_MAX_TOKENS: int = 3000  # 规划阶段专用最大token数（JSON结构较大，需要更多token防止截断）
    LLM_TIMEOUT: int = 120  # LLM API请求超时时间（秒）
    LLM_MAX_CONTEXT_CHARS: int = 5000  # 传入LLM的最大上下文字符数

    # ==================== RAG评估配置 ====================
    EVAL_LLM_MODEL: str = "qwen-turbo"  # 评估专用轻量模型，空字符串则复用 LLM_MODEL
    EVAL_LLM_API_KEY: str = ""  # 评估专用API密钥（空字符串则复用 LLM_API_KEY）
    EVAL_LLM_API_BASE: str = ""  # 评估专用API地址（空字符串则复用 LLM_API_BASE）
    EVAL_LLM_MAX_TOKENS: int = 300  # 评估时答案不需要太长，节省token
    EVAL_SKIP_LLM: bool = True  # 是否跳过LLM生成，只计算检索指标；日常调参建议设为 True
    EVAL_TOP_K: int = 5  # 评估时的检索返回数量，覆盖 TOP_K_DEFAULT
    BASELINE_FILE: str = "rag_baseline.json"  # RAG回归测试基准文件路径
    
    # ==================== 多路召回与重排序配置 ====================
    BM25_WEIGHT: float = 0.3  # BM25检索权重（与向量检索权重相加应为1.0）
    VECTOR_WEIGHT: float = 0.7  # 向量检索权重
    RERANK_TOP_N: int = 10  # 重排序前候选数量（从多路召回结果中取前N个进行精排）
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"  # 重排序模型名称（bge-reranker-v2-m3 支持中英双语，性能更强）
    RERANKER_LOCAL_PATH: str = "./model/bge-reranker-v2-m3"  # 本地模型路径（如果已下载到本地）
    ENABLE_MULTI_RETRIEVAL: bool = True  # 是否启用多路召回
    ENABLE_BM25: bool = True  # 是否启用BM25检索
    ENABLE_RERANK: bool = True  # 是否启用重排序

    # ==================== Query Rewrite 配置 ====================
    ENABLE_QUERY_REWRITE: bool = False  # 未经评测，不进入正式 Agent 检索路径
    ENABLE_HYDE: bool = False           # 可选实验，默认关闭
    ENABLE_MULTI_QUERY: bool = False    # 可选实验，默认关闭
    ENABLE_STEP_BACK: bool = False      # 可选实验，默认关闭
    QUERY_REWRITE_MAX_QUERIES: int = 5  # 最多并发检索的扩展 query 数量（防止 token 爆炸）
    QUERY_REWRITE_ONLY_COMPLEX: bool = True  # True=只对复杂查询做 Rewrite，False=所有查询
    
    # ==================== 检索策略配置 ====================
    RETRIEVAL_STRATEGY: str = "A"  # 当前正式链路：PostgreSQL BM25 + Milvus dense + 加权融合 + Reranker
    RRF_K: int = 60  # RRF融合参数（经典值为60）
    ENABLE_SPARSE_RETRIEVAL: bool = False  # 暂不启用 Milvus/BGE-M3 稀疏向量检索
    
    # ==================== Milvus向量数据库配置 ====================
    MILVUS_URI: str = "http://localhost:19530"  # Milvus连接URI，Docker部署使用"http://localhost:19530"
    MILVUS_TOKEN: str = ""  # Milvus认证令牌（Zilliz Cloud时需要）
    MILVUS_COLLECTION_NAME: str = "meetingmind_docs"  # Milvus集合名称
    VECTOR_COLLECTION_NAME: str = "meetingmind_docs"  # 向量集合名称（供 MilvusVectorStore 使用）
    USE_GPU: bool = True  # 是否使用GPU加速（RTX 4060）
    USE_FP16: bool = True  # 是否使用FP16精度（GPU可用时开启，加速推理）
    BGE_M3_MODEL_PATH: str = "F:/project/meetingmind-agent/backend/model/bge-m3"  # BGE-M3本地模型路径
    
    # ==================== 多模态服务配置 ====================
    VISION_API_BASE: str = "https://api.openai.com/v1"  # 视觉API基础URL
    VISION_API_KEY: str = ""  # Vision API密钥
    VISION_MODEL: str = "gpt-4o"  # 视觉模型名称
    VISION_MAX_TOKENS: int = 1000  # Vision最大token数
    WHISPER_API_BASE: str = "https://api.openai.com/v1"  # Whisper API基础URL
    WHISPER_API_KEY: str = ""  # Whisper API密钥
    WHISPER_MODEL: str = "whisper-1"  # Whisper模型名称
    ENABLE_MULTIMODAL: bool = False  # 真实 ASR 接入前，多模态骨架默认关闭
    MULTIMODAL_MAX_IMAGE_SIZE_MB: int = 10  # 图片最大大小（MB）
    MULTIMODAL_MAX_AUDIO_SIZE_MB: int = 50  # 音频最大大小（MB）
    MULTIMODAL_SUPPORTED_FORMATS: str = "png,jpg,jpeg,gif,webp,bmp,mp3,wav,m4a,ogg,flac,pdf,docx,txt,md"
    MULTIMODAL_ENABLE_SAFETY_CHECK: bool = True  # 是否启用多模态安全检测

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
    ENABLE_SEMANTIC_RISK_CHECK: bool = True  # 是否启用语义风险检测
    SEMANTIC_RISK_MODEL: str = "gpt-4o-mini"  # 语义检测用的模型
    SEMANTIC_RISK_TIMEOUT_MS: int = 3000  # 语义检测超时
    ENABLE_INJECTION_GUARD: bool = True  # 是否启用 Prompt Injection 防护
    INJECTION_GUARD_DEPTH: str = "light"  # light/heavy 检测深度
    INJECTION_GUARD_LOG_ALL: bool = True  # 是否记录所有检测尝试

    # ==================== Agent规划配置 ====================
    ENABLE_TEMPLATE_PLANNING: bool = True  # 是否启用任务模板库（优先匹配模板，失败再用LLM）
    ENABLE_PLAN_VALIDATION: bool = True  # 是否启用规划验证（语法、逻辑、质量检查）
    ENABLE_PLAN_AUTO_FIX: bool = True  # 是否启用计划自动修复
    TEMPLATE_MATCH_THRESHOLD: float = 0.2  # 模板匹配阈值（0-1）
    MAX_TASKS_IN_PLAN: int = 10  # 计划中最大任务数量

    # ==================== 并行执行配置 ====================
    ENABLE_PARALLEL_EXECUTOR: bool = True  # 是否启用并行执行引擎
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
    ENABLE_UNIFIED_QUALITY_GATE: bool = True  # 是否启用统一质量门禁（替代 replan+reflection 双重评估）
    QUALITY_GATE_REPLAN_THRESHOLD: float = 0.5  # 触发重规划的分数阈值
    QUALITY_GATE_POLISH_THRESHOLD: float = 0.7  # 触发抛光的分数阈值

    # ==================== HITL 细粒度风险控制配置 ====================
    HITL_MIN_RISK_LEVEL: str = "HIGH"  # 触发人工确认的最低风险等级（LOW/MEDIUM/HIGH/CRITICAL）
    HITL_AUTO_APPROVE_LOW: bool = True  # LOW 风险自动放行（不弹确认）
    HITL_AUTO_APPROVE_MEDIUM: bool = True  # MEDIUM 风险自动放行（不弹确认）

    # ==================== 确定性错误检查配置 ====================
    ENABLE_DETERMINISTIC_CHECK: bool = True  # 是否启用确定性错误检查（反思前置）
    ENABLE_CROSS_MODEL_VALIDATION: bool = False  # 是否启用跨模型交叉验证

    # ==================== 反思记忆配置 ====================
    ENABLE_REFLECTION_MEMORY: bool = False  # 可选实验，不进入默认答案路径
    REFLECTION_MEMORY_TOP_K: int = 3  # 查询相似反思的最大数量
    REFLECTION_MEMORY_ASYNC: bool = True  # 是否异步写入（不阻塞主流程）
    REFLECTION_MEMORY_CACHE_SIZE: int = 500  # 内存缓存大小
    REFLECTION_MEMORY_CACHE_TTL: int = 3600  # 缓存过期时间（秒）

    
    # ==================== 知识图谱配置 ====================
    ENABLE_KNOWLEDGE_GRAPH: bool = False  # 可选增强默认关闭，不改变正式 RAG 主链路
    KNOWLEDGE_GRAPH_DEPTH: int = 2  # 图谱扩展深度
    KNOWLEDGE_GRAPH_MIN_SCORE: float = 0.3  # 图谱扩展结果的最低分数阈值
    
    # ==================== Neo4j 图数据库配置 ====================
    NEO4J_URI: str = "bolt://neo4j:7687"  # Neo4j Bolt 连接地址
    NEO4J_USER: str = "neo4j"  # Neo4j 用户名
    NEO4J_PASSWORD: str = "password"  # Neo4j 密码
    NEO4J_DATABASE: str = "neo4j"  # 数据库名称
    ENABLE_NEO4J_PERSISTENCE: bool = False  # 随 KG 默认关闭

    # ==================== MCP Server 配置 ====================
    ENABLE_MCP_SERVER: bool = False  # 接入一个真实外部 Server 后再显式开启
    MCP_SERVER_PATH: str = "/mcp"  # MCP Server 挂载路径

    # ==================== 后台消费者配置 ====================
    ENABLE_AGENT_WORKER: bool = False  # 需要 RabbitMQ 的 Agent 消费者显式启动

    # 飞书 MCP 配置
    FEISHU_MCP_ENABLED: bool = False  # 是否启用飞书 MCP
    FEISHU_MCP_URL: str = ""  # 飞书 MCP 服务器地址
    FEISHU_MCP_APP_ID: str = ""  # 飞书应用 ID
    FEISHU_MCP_APP_SECRET: str = ""  # 飞书应用密钥

    # GitHub MCP 配置
    GITHUB_MCP_ENABLED: bool = False  # 是否启用 GitHub MCP
    GITHUB_MCP_URL: str = ""  # GitHub MCP 服务器地址
    GITHUB_MCP_TOKEN: str = ""  # GitHub Access Token

    # Jira Cloud REST v3 配置（保留 JIRA_MCP_* 名称以兼容已有 .env）
    JIRA_MCP_ENABLED: bool = False  # 仅凭据齐全并计划真实调用时开启
    JIRA_MCP_URL: str = ""  # 站点地址，例如 https://example.atlassian.net
    JIRA_MCP_USERNAME: str = ""  # Atlassian 账号邮箱
    JIRA_MCP_API_TOKEN: str = ""  # Atlassian API Token，禁止提交到 Git
    JIRA_HTTP_TIMEOUT_SECONDS: float = 15.0
    JIRA_MAX_RETRIES: int = 2  # 仅用于 GET/PUT 等幂等请求
    JIRA_MAX_RETRY_DELAY_SECONDS: float = 10.0

    # Notion MCP 配置
    NOTION_MCP_ENABLED: bool = False  # 是否启用 Notion MCP
    NOTION_MCP_URL: str = ""  # Notion MCP 服务器地址
    NOTION_MCP_API_KEY: str = ""  # Notion API Key

    # 邮件发送配置
    SMTP_SERVER: str = "smtp.example.com"  # SMTP服务器地址
    SMTP_PORT: int = 587  # SMTP端口
    SMTP_USER: str = ""  # SMTP用户名
    SMTP_PASSWORD: str = ""  # SMTP密码
    SMTP_FROM_EMAIL: str = "meetingmind@example.com"  # 发件人邮箱

    @model_validator(mode="after")
    def validate_production_secrets(self):
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
    def BASELINE_FILE_ABSOLUTE(self) -> str:
        """获取RAG回归测试基准文件的绝对路径"""
        import os
        backend_dir = self._get_backend_dir()
        # 如果是相对路径，转换为绝对路径
        baseline_file = self.BASELINE_FILE
        if not os.path.isabs(baseline_file):
            baseline_file = os.path.join(backend_dir, baseline_file)
            baseline_file = os.path.normpath(baseline_file)
        return baseline_file

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    @property
    def allowed_file_extensions_list(self) -> List[str]:
        return json.loads(self.ALLOWED_FILE_EXTENSIONS)


settings = Settings()
