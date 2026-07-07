"""工具元数据结构定义"""
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

class ToolCategory(str, Enum):
    """工具分类"""
    # 基础工具
    SEARCH = "search"  # 搜索工具
    RETRIEVE = "retrieve"  # 读取类
    RETRIEVAL = "retrieval"  # 检索工具
    COMPUTATION = "computation"  # 计算工具
    GENERATE = "generate"  # 生成类
    EXTRACT = "extract"  # 抽取类
    FORMAT = "format"  # 格式化类
    UTILITY = "utility"  # 工具类
    
    # 会议专用
    MEETING = "meeting"  # 会议相关
    MINUTES = "minutes"  # 会议纪要
    TODO = "todo"  # 待办事项
    
    # 文档工具
    DOCUMENT = "document"  # 文档相关
    KNOWLEDGE = "knowledge"  # 知识库
    
    # 信息工具
    INFO = "info"  # 信息查询
    CALCULATOR = "calculator"  # 计算器
    TRANSLATOR = "translator"  # 翻译
    
    # 协作工具
    COLLABORATION = "collaboration"  # 协作
    NOTIFICATION = "notification"  # 通知
    
    # 自定义
    CUSTOM = "custom"  # 自定义工具

class ToolStatus(str, Enum):
    """工具状态"""
    ACTIVE = "active"  # 活跃
    INACTIVE = "inactive"  # 停用
    DEPRECATED = "deprecated"  # 已废弃
    BETA = "beta"  # 测试中

class ToolRiskLevel(str, Enum):
    """工具风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str  # 参数名
    type: str  # 参数类型 (string, integer, float, boolean, array, object)
    description: str  # 参数描述
    required: bool = True  # 是否必需
    default: Any = None  # 默认值
    enum_values: List[Any] = None  # 枚举值
    min_value: float = None  # 最小值（数字类型）
    max_value: float = None  # 最大值（数字类型）
    
    def __post_init__(self):
        if self.enum_values is None:
            self.enum_values = []
    
    def validate(self, value: Any) -> tuple[bool, str]:
        """验证参数值"""
        if value is None:
            if self.required:
                return False, f"参数 {self.name} 是必需的"
            return True, ""
        
        # 类型检查
        type_mapping = {
            "string": str,
            "integer": int,
            "float": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected_type = type_mapping.get(self.type)
        if expected_type and not isinstance(value, expected_type):
            return False, f"参数 {self.name} 类型错误，期望 {self.type}"
        
        # 枚举值检查
        if self.enum_values and value not in self.enum_values:
            return False, f"参数 {self.name} 值必须在 {self.enum_values} 中"
        
        # 范围检查
        if self.type in ["integer", "float"] and value is not None:
            if self.min_value is not None and value < self.min_value:
                return False, f"参数 {self.name} 不能小于 {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"参数 {self.name} 不能大于 {self.max_value}"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "enum_values": self.enum_values,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

@dataclass
class ToolCondition:
    """工具触发条件"""
    type: str  # condition_type: keyword, entity, context, regex, semantic
    value: str  # 条件值
    operator: str = "contains"  # contains, equals, starts_with, ends_with, matches
    weight: float = 1.0  # 条件权重
    required: bool = False  # 是否必需
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """评估条件是否满足"""
        if self.type == "keyword":
            text = context.get("query", "") + " " + context.get("context", "")
            text = text.lower()
            value = self.value.lower()
            if self.operator == "contains":
                return value in text
            elif self.operator == "equals":
                return text == value
            elif self.operator == "starts_with":
                return text.startswith(value)
            elif self.operator == "ends_with":
                return text.endswith(value)
        elif self.type == "entity":
            entities = context.get("entities", [])
            return self.value in entities
        elif self.type == "context":
            return context.get(self.value) is not None
        elif self.type == "regex":
            import re
            text = context.get("query", "") + " " + context.get("context", "")
            return bool(re.search(self.value, text))
        elif self.type == "semantic":
            return True
        return False


@dataclass
class ToolCombinationRule:
    """工具组合规则"""
    rule_id: str
    tool_ids: List[str]  # 组合的工具ID列表
    execution_order: str = "sequential"  # sequential, parallel
    condition: Optional[str] = None  # 触发条件
    expected_input: Dict[str, Any] = field(default_factory=dict)
    expected_output: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    priority: int = 0


@dataclass
class ToolMetadata:
    """工具元数据"""
    tool_id: str  # 工具唯一ID
    name: str  # 工具名称（人类可读）
    description: str  # 工具描述
    category: ToolCategory  # 工具分类
    tags: List[str] = field(default_factory=list)  # 标签
    version: str = "1.0.0"  # 版本号
    author: str = ""  # 作者
    status: ToolStatus = ToolStatus.ACTIVE  # 状态
    parameters: List[ToolParameter] = field(default_factory=list)  # 参数列表
    return_type: str = "string"  # 返回类型
    examples: List[Dict[str, Any]] = field(default_factory=list)  # 使用示例
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他工具
    rate_limit: int = 100  # 速率限制（次/分钟）
    timeout: int = 30  # 超时时间（秒）
    cost: float = 0.0  # 每次调用成本
    risk_level: ToolRiskLevel | str = ToolRiskLevel.LOW  # 工具风险等级
    requires_confirmation: bool = False  # 执行前是否需要人工确认
    idempotent: bool = True  # 重复执行是否不会产生额外副作用
    allowed_workflows: List[str] = field(default_factory=list)  # 允许使用的工作流
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间
    
    # 使用统计
    call_count: int = 0  # 调用次数
    success_count: int = 0  # 成功次数
    failure_count: int = 0  # 失败次数
    avg_execution_time: float = 0.0  # 平均执行时间（秒）
    
    # 功能标志
    supports_streaming: bool = False  # 是否支持流式输出
    requires_auth: bool = False  # 是否需要认证
    is_async: bool = False  # 是否异步执行
    cacheable: bool = False  # 结果是否可缓存
    
    # 动态工具选择相关
    conditions: List[ToolCondition] = field(default_factory=list)  # 触发条件
    combination_rules: List[ToolCombinationRule] = field(default_factory=list)  # 组合规则
    input_schema: Dict[str, Any] = field(default_factory=dict)  # 输入数据schema
    output_schema: Dict[str, Any] = field(default_factory=dict)  # 输出数据schema
    compatibility_tags: List[str] = field(default_factory=list)  # 兼容性标签
    exclusion_tags: List[str] = field(default_factory=list)  # 互斥标签
    
    def __post_init__(self):
        if not self.tags:
            self.tags = []
        if not self.parameters:
            self.parameters = []
        if not self.examples:
            self.examples = []
        if not self.dependencies:
            self.dependencies = []
        if not self.allowed_workflows:
            self.allowed_workflows = []
        if not self.conditions:
            self.conditions = []
        if not self.combination_rules:
            self.combination_rules = []
        if not self.compatibility_tags:
            self.compatibility_tags = []
        if not self.exclusion_tags:
            self.exclusion_tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value if isinstance(self.category, ToolCategory) else self.category,
            "tags": self.tags,
            "version": self.version,
            "author": self.author,
            "status": self.status.value if isinstance(self.status, ToolStatus) else self.status,
            "parameters": [p.to_dict() if isinstance(p, ToolParameter) else p for p in self.parameters],
            "return_type": self.return_type,
            "examples": self.examples,
            "dependencies": self.dependencies,
            "rate_limit": self.rate_limit,
            "timeout": self.timeout,
            "cost": self.cost,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, ToolRiskLevel) else self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "idempotent": self.idempotent,
            "allowed_workflows": self.allowed_workflows,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "usage_stats": {
                "call_count": self.call_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "avg_execution_time": self.avg_execution_time,
                "success_rate": self.success_count / self.call_count if self.call_count > 0 else 0,
            },
            "features": {
                "supports_streaming": self.supports_streaming,
                "requires_auth": self.requires_auth,
                "is_async": self.is_async,
                "cacheable": self.cacheable,
            },
            "dynamic": {
                "conditions": [{"type": c.type, "value": c.value, "operator": c.operator, "weight": c.weight, "required": c.required} for c in self.conditions],
                "combination_rules": [{"rule_id": r.rule_id, "tool_ids": r.tool_ids, "execution_order": r.execution_order, "priority": r.priority} for r in self.combination_rules],
                "compatibility_tags": self.compatibility_tags,
                "exclusion_tags": self.exclusion_tags,
            },
        }
    
    def evaluate_conditions(self, context: Dict[str, Any]) -> float:
        """评估触发条件，返回匹配分数"""
        if not self.conditions:
            return 1.0
        
        total_weight = sum(c.weight for c in self.conditions)
        matched_weight = 0.0
        
        for condition in self.conditions:
            if condition.evaluate(context):
                matched_weight += condition.weight
        
        if total_weight == 0:
            return 1.0
        
        return matched_weight / total_weight
    
    def validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, List[str]]:
        """验证参数列表"""
        errors = []
        
        for param_def in self.parameters:
            if isinstance(param_def, ToolParameter):
                value = params.get(param_def.name)
                is_valid, error_msg = param_def.validate(value)
                if not is_valid:
                    errors.append(error_msg)
        
        return len(errors) == 0, errors
    
    def update_stats(self, success: bool, execution_time: float):
        """更新使用统计"""
        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        
        # 更新平均执行时间
        if self.call_count > 0:
            self.avg_execution_time = (
                (self.avg_execution_time * (self.call_count - 1) + execution_time) / self.call_count
            )
        
        self.updated_at = datetime.now()

@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    tool_id: str
    success: bool
    result: Any = None
    error: str = ""
    execution_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_id": self.tool_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "cached": self.cached,
            "metadata": self.metadata,
        }

class Tool:
    """
    工具基类
    
    所有工具都需要继承此类，并实现 execute 方法
    """
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
        self._func: Optional[Callable] = None
    
    def set_function(self, func: Callable):
        """设置实际执行的函数"""
        self._func = func
        return self
    
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        """执行工具"""
        import time
        start_time = time.time()
        
        # 验证参数
        is_valid, errors = self.metadata.validate_parameters(params)
        if not is_valid:
            return ToolExecutionResult(
                tool_id=self.metadata.tool_id,
                success=False,
                error="参数验证失败: " + "; ".join(errors),
                execution_time=time.time() - start_time,
            )
        
        try:
            # 执行函数
            if self._func:
                if self.metadata.is_async:
                    result = await self._func(**params)
                else:
                    result = self._func(**params)
            else:
                result = await self._execute_impl(params, context)
            
            execution_time = time.time() - start_time
            
            # 更新统计
            self.metadata.update_stats(success=True, execution_time=execution_time)
            
            return ToolExecutionResult(
                tool_id=self.metadata.tool_id,
                success=True,
                result=result,
                execution_time=execution_time,
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.metadata.update_stats(success=False, execution_time=execution_time)
            
            return ToolExecutionResult(
                tool_id=self.metadata.tool_id,
                success=False,
                error=str(e),
                execution_time=execution_time,
            )
    
    async def _execute_impl(self, params: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Any:
        """实际执行逻辑，子类需要重写"""
        raise NotImplementedError("子类必须实现 _execute_impl 方法")
    
    def get_schema(self) -> Dict[str, Any]:
        """获取工具的OpenAI格式schema"""
        properties = {}
        required = []
        
        for param in self.metadata.parameters:
            if isinstance(param, ToolParameter):
                param_dict = {"description": param.description}
                
                if param.type == "string":
                    param_dict["type"] = "string"
                elif param.type == "integer":
                    param_dict["type"] = "integer"
                elif param.type == "float":
                    param_dict["type"] = "number"
                elif param.type == "boolean":
                    param_dict["type"] = "boolean"
                elif param.type == "array":
                    param_dict["type"] = "array"
                elif param.type == "object":
                    param_dict["type"] = "object"
                
                if param.enum_values:
                    param_dict["enum"] = param.enum_values
                
                properties[param.name] = param_dict
                
                if param.required:
                    required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.metadata.tool_id,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
