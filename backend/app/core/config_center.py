"""统一配置中心 - 支持多源配置、动态加载、热更新"""
import os
import json
from typing import Any, Dict, Optional, List, Type
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
from functools import lru_cache
from app.core.logger import app_logger


class ConfigSource(str, Enum):
    """配置来源枚举"""
    ENV = "env"
    DATABASE = "database"
    FILE = "file"
    DEFAULT = "default"


@dataclass
class ConfigItem:
    """配置项定义"""
    key: str
    value: Any
    description: str
    category: str
    source: ConfigSource
    data_type: str
    default_value: Any = None
    required: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    enum_values: Optional[List[Any]] = None
    updated_at: Optional[datetime] = None


class ConfigCategory(str, Enum):
    """配置分类"""
    APP = "app"
    DATABASE = "database"
    CORS = "cors"
    UPLOAD = "upload"
    PROCESSING = "processing"
    LOG = "log"
    CACHE = "cache"
    EMBEDDING = "embedding"
    LLM = "llm"
    RAG = "rag"
    AGENT = "agent"


class ConfigCenter:
    """统一配置中心"""
    
    def __init__(self):
        self._configs: Dict[str, ConfigItem] = {}
        self._overrides: Dict[str, Any] = {}  # 运行时覆盖
        self._listeners: List[callable] = []  # 配置变更监听器
        self._initialized = False
    
    def initialize(self):
        """初始化配置中心"""
        if self._initialized:
            return
        
        self._load_defaults()
        self._load_from_env()
        self._load_from_database()
        
        self._initialized = True
        app_logger.info("[ConfigCenter] 配置中心初始化完成")
    
    def _load_defaults(self):
        """加载默认配置"""
        defaults = [
            # 应用配置
            ConfigItem(
                key="app.name",
                value="MeetingMind",
                description="应用名称",
                category=ConfigCategory.APP,
                source=ConfigSource.DEFAULT,
                data_type="str"
            ),
            ConfigItem(
                key="app.env",
                value="development",
                description="运行环境",
                category=ConfigCategory.APP,
                source=ConfigSource.DEFAULT,
                data_type="str",
                enum_values=["development", "production", "test"]
            ),
            ConfigItem(
                key="app.debug",
                value=False,
                description="DEBUG模式",
                category=ConfigCategory.APP,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="app.secret_key",
                value="meetingmind-secret-key-change-in-production",
                description="密钥",
                category=ConfigCategory.APP,
                source=ConfigSource.DEFAULT,
                data_type="str",
                required=True
            ),
            ConfigItem(
                key="app.access_token_expire_minutes",
                value=60,
                description="JWT过期时间(分钟)",
                category=ConfigCategory.APP,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            
            # 数据库配置
            ConfigItem(
                key="database.url",
                value="postgresql+asyncpg://postgres:123456@localhost:5432/meetingmind",
                description="数据库连接字符串",
                category=ConfigCategory.DATABASE,
                source=ConfigSource.DEFAULT,
                data_type="str",
                required=True
            ),
            
            # Redis配置
            ConfigItem(
                key="cache.redis_url",
                value="redis://localhost:6379/0",
                description="Redis连接字符串",
                category=ConfigCategory.CACHE,
                source=ConfigSource.DEFAULT,
                data_type="str"
            ),
            ConfigItem(
                key="cache.ttl",
                value=300,
                description="缓存过期时间(秒)",
                category=ConfigCategory.CACHE,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=0
            ),
            ConfigItem(
                key="cache.enabled",
                value=False,
                description="是否启用缓存",
                category=ConfigCategory.CACHE,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            
            # LLM配置
            ConfigItem(
                key="llm.api_base",
                value="https://dashscope.aliyuncs.com/compatible-mode/v1",
                description="LLM API基础URL",
                category=ConfigCategory.LLM,
                source=ConfigSource.DEFAULT,
                data_type="str"
            ),
            ConfigItem(
                key="llm.model",
                value="qwen3.6-plus",
                description="LLM模型名称",
                category=ConfigCategory.LLM,
                source=ConfigSource.DEFAULT,
                data_type="str"
            ),
            ConfigItem(
                key="llm.temperature",
                value=0.7,
                description="温度参数",
                category=ConfigCategory.LLM,
                source=ConfigSource.DEFAULT,
                data_type="float",
                min_value=0.0,
                max_value=1.0
            ),
            ConfigItem(
                key="llm.max_tokens",
                value=1000,
                description="最大token数",
                category=ConfigCategory.LLM,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            ConfigItem(
                key="llm.timeout",
                value=20,
                description="超时时间(秒)",
                category=ConfigCategory.LLM,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            
            # 向量化配置
            ConfigItem(
                key="embedding.model",
                value="BAAI/bge-m3",
                description="嵌入模型",
                category=ConfigCategory.EMBEDDING,
                source=ConfigSource.DEFAULT,
                data_type="str"
            ),
            ConfigItem(
                key="embedding.device",
                value="cuda",
                description="计算设备",
                category=ConfigCategory.EMBEDDING,
                source=ConfigSource.DEFAULT,
                data_type="str",
                enum_values=["cpu", "cuda"]
            ),
            ConfigItem(
                key="embedding.top_k",
                value=5,
                description="检索返回数量",
                category=ConfigCategory.EMBEDDING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            ConfigItem(
                key="embedding.similarity_threshold",
                value=0.7,
                description="相似度阈值",
                category=ConfigCategory.EMBEDDING,
                source=ConfigSource.DEFAULT,
                data_type="float",
                min_value=0.0,
                max_value=1.0
            ),
            
            # RAG配置
            ConfigItem(
                key="rag.bm25_weight",
                value=0.3,
                description="BM25权重",
                category=ConfigCategory.RAG,
                source=ConfigSource.DEFAULT,
                data_type="float",
                min_value=0.0,
                max_value=1.0
            ),
            ConfigItem(
                key="rag.vector_weight",
                value=0.7,
                description="向量权重",
                category=ConfigCategory.RAG,
                source=ConfigSource.DEFAULT,
                data_type="float",
                min_value=0.0,
                max_value=1.0
            ),
            ConfigItem(
                key="rag.enable_multi_retrieval",
                value=True,
                description="启用多路召回",
                category=ConfigCategory.RAG,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="rag.enable_rerank",
                value=True,
                description="启用重排序",
                category=ConfigCategory.RAG,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            
            # Agent配置
            ConfigItem(
                key="agent.enable_template_planning",
                value=True,
                description="启用模板规划",
                category=ConfigCategory.AGENT,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="agent.max_tasks",
                value=10,
                description="最大任务数",
                category=ConfigCategory.AGENT,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            ConfigItem(
                key="agent.enable_human_in_the_loop",
                value=False,
                description="启用人机协作",
                category=ConfigCategory.AGENT,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            
            # 文本处理配置
            ConfigItem(
                key="processing.chunk_size",
                value=512,
                description="切片大小",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=10
            ),
            ConfigItem(
                key="processing.chunk_overlap",
                value=64,
                description="切片重叠",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=0
            ),
            ConfigItem(
                key="processing.enable_semantic_chunking",
                value=False,
                description="文档上传流程启用语义分块",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="processing.semantic_chunk_strategy",
                value="semantic_hybrid",
                description="语义分块策略",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="str",
                enum_values=["semantic", "semantic_hybrid", "paragraph", "fixed_size"]
            ),
            ConfigItem(
                key="processing.semantic_chunk_use_llm",
                value=False,
                description="语义分块允许调用LLM",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="processing.semantic_chunk_min_size",
                value=100,
                description="语义块最小大小",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            ConfigItem(
                key="processing.semantic_chunk_max_size",
                value=1000,
                description="语义块最大大小",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=1
            ),
            ConfigItem(
                key="processing.semantic_chunk_overlap",
                value=50,
                description="语义分块降级固定切分重叠",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="int",
                min_value=0
            ),
            ConfigItem(
                key="processing.semantic_chunk_build_hierarchy",
                value=True,
                description="语义分块构建父子层级",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
            ConfigItem(
                key="processing.semantic_chunk_preserve_structure",
                value=True,
                description="语义分块保留标题结构",
                category=ConfigCategory.PROCESSING,
                source=ConfigSource.DEFAULT,
                data_type="bool"
            ),
        ]
        
        for item in defaults:
            self._configs[item.key] = item
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mappings = {
            "APP_NAME": "app.name",
            "APP_ENV": "app.env",
            "DEBUG": "app.debug",
            "SECRET_KEY": "app.secret_key",
            "DATABASE_URL": "database.url",
            "REDIS_URL": "cache.redis_url",
            "LLM_API_BASE": "llm.api_base",
            "LLM_API_KEY": "llm.api_key",
            "LLM_MODEL": "llm.model",
            "LLM_TEMPERATURE": "llm.temperature",
            "LLM_MAX_TOKENS": "llm.max_tokens",
            "EMBEDDING_MODEL": "embedding.model",
            "EMBEDDING_DEVICE": "embedding.device",
            "ENABLE_SEMANTIC_CHUNKING": "processing.enable_semantic_chunking",
            "SEMANTIC_CHUNK_STRATEGY": "processing.semantic_chunk_strategy",
            "SEMANTIC_CHUNK_USE_LLM": "processing.semantic_chunk_use_llm",
            "SEMANTIC_CHUNK_MIN_SIZE": "processing.semantic_chunk_min_size",
            "SEMANTIC_CHUNK_MAX_SIZE": "processing.semantic_chunk_max_size",
            "SEMANTIC_CHUNK_OVERLAP": "processing.semantic_chunk_overlap",
            "SEMANTIC_CHUNK_BUILD_HIERARCHY": "processing.semantic_chunk_build_hierarchy",
            "SEMANTIC_CHUNK_PRESERVE_STRUCTURE": "processing.semantic_chunk_preserve_structure",
        }
        
        for env_key, config_key in env_mappings.items():
            value = os.getenv(env_key)
            if value is not None:
                if config_key in self._configs:
                    item = self._configs[config_key]
                    parsed_value = self._parse_value(value, item.data_type)
                    if parsed_value is not None:
                        self._configs[config_key] = ConfigItem(
                            **{**asdict(item), "value": parsed_value, "source": ConfigSource.ENV}
                        )
                        app_logger.debug(f"[ConfigCenter] 从环境变量加载: {config_key}")
    
    def _load_from_database(self):
        """从数据库加载配置（预留）"""
        try:
            from app.db.database import get_db
            from app.models.config import ConfigModel
            # 数据库配置加载逻辑（延迟加载以避免循环依赖）
            app_logger.debug("[ConfigCenter] 尝试从数据库加载配置")
        except Exception as e:
            app_logger.debug(f"[ConfigCenter] 数据库配置加载失败（可能尚未初始化）: {e}")
    
    def _parse_value(self, value: str, data_type: str) -> Any:
        """解析字符串值到指定类型"""
        try:
            if data_type == "int":
                return int(value)
            elif data_type == "float":
                return float(value)
            elif data_type == "bool":
                return value.lower() in ("true", "1", "yes", "on")
            elif data_type == "json":
                return json.loads(value)
            else:
                return value
        except ValueError:
            return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if not self._initialized:
            self.initialize()
        
        # 先检查运行时覆盖
        if key in self._overrides:
            return self._overrides[key]
        
        # 检查配置项
        if key in self._configs:
            return self._configs[key].value
        
        return default
    
    def get_config_item(self, key: str) -> Optional[ConfigItem]:
        """获取完整配置项"""
        if not self._initialized:
            self.initialize()
        return self._configs.get(key)
    
    def set(self, key: str, value: Any, source: ConfigSource = ConfigSource.DATABASE) -> bool:
        """设置配置值（运行时）"""
        if not self._initialized:
            self.initialize()
        
        if key not in self._configs:
            app_logger.warning(f"[ConfigCenter] 配置项不存在: {key}")
            return False
        
        item = self._configs[key]
        
        # 验证值
        if not self._validate_value(value, item):
            app_logger.warning(f"[ConfigCenter] 配置值验证失败: {key} = {value}")
            return False
        
        # 更新运行时覆盖
        self._overrides[key] = value
        
        # 更新配置项
        self._configs[key] = ConfigItem(
            **{**asdict(item), "value": value, "source": source, "updated_at": datetime.now()}
        )
        
        # 触发监听器
        self._notify_listeners(key, value)
        
        app_logger.info(f"[ConfigCenter] 配置更新: {key} = {value}")
        return True
    
    def _validate_value(self, value: Any, item: ConfigItem) -> bool:
        """验证配置值"""
        if item.data_type == "int":
            if not isinstance(value, int):
                return False
            if item.min_value is not None and value < item.min_value:
                return False
            if item.max_value is not None and value > item.max_value:
                return False
        elif item.data_type == "float":
            if not isinstance(value, (int, float)):
                return False
            if item.min_value is not None and value < item.min_value:
                return False
            if item.max_value is not None and value > item.max_value:
                return False
        elif item.data_type == "bool":
            if not isinstance(value, bool):
                return False
        elif item.enum_values and value not in item.enum_values:
            return False
        
        return True
    
    def _notify_listeners(self, key: str, value: Any):
        """通知所有监听器配置变更"""
        for listener in self._listeners:
            try:
                listener(key, value)
            except Exception as e:
                app_logger.error(f"[ConfigCenter] 监听器调用失败: {e}")
    
    def add_listener(self, listener: callable):
        """添加配置变更监听器"""
        self._listeners.append(listener)
    
    def remove_listener(self, listener: callable):
        """移除配置变更监听器"""
        self._listeners.remove(listener)
    
    def get_by_category(self, category: ConfigCategory) -> List[ConfigItem]:
        """按分类获取配置"""
        if not self._initialized:
            self.initialize()
        
        return [item for item in self._configs.values() if item.category == category]
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置值"""
        if not self._initialized:
            self.initialize()
        
        result = {}
        for key, item in self._configs.items():
            # 敏感配置脱敏
            if "key" in key.lower() or "secret" in key.lower():
                if isinstance(item.value, str) and len(item.value) > 8:
                    result[key] = item.value[:4] + "****" + item.value[-4:]
                else:
                    result[key] = "***"
            else:
                result[key] = item.value
        
        return result
    
    def get_full_configs(self) -> List[Dict[str, Any]]:
        """获取所有配置项的完整信息"""
        if not self._initialized:
            self.initialize()
        
        result = []
        for item in self._configs.values():
            data = asdict(item)
            # 敏感配置脱敏
            if "key" in item.key.lower() or "secret" in item.key.lower():
                if isinstance(data["value"], str) and len(data["value"]) > 8:
                    data["value"] = data["value"][:4] + "****" + data["value"][-4:]
                else:
                    data["value"] = "***"
            result.append(data)
        
        return result
    
    def reload(self):
        """重新加载配置"""
        self._overrides.clear()
        self._configs.clear()
        self._initialized = False
        self.initialize()
        app_logger.info("[ConfigCenter] 配置已重新加载")


# 全局配置中心实例
config_center = ConfigCenter()


def get_config_center() -> ConfigCenter:
    """获取配置中心实例"""
    return config_center


# 便捷函数
def get_config(key: str, default: Any = None) -> Any:
    """便捷获取配置"""
    return config_center.get(key, default)
