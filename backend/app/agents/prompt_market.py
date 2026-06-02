"""Prompt模板市场 - 支持会议场景领域配置化"""
import json
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from app.core.logger import app_logger


class TemplateCategory(str, Enum):
    """模板分类"""
    MEETING_SUMMARY = "meeting_summary"      # 会议总结
    ACTION_ITEM = "action_item"              # 待办事项
    DECISION_RECORD = "decision_record"      # 决策记录
    CONTROVERSY = "controversy"              # 争议分析
    QA_ANALYSIS = "qa_analysis"              # 问答分析
    MEETING_PLAN = "meeting_plan"            # 会议规划
    FOLLOW_UP = "follow_up"                  # 跟进提醒
    CUSTOM = "custom"                        # 自定义


class TemplateType(str, Enum):
    """模板类型"""
    SYSTEM = "system"    # 系统模板
    USER = "user"        # 用户自定义
    SHARED = "shared"    # 共享模板


@dataclass
class PromptTemplate:
    """Prompt模板结构"""
    template_id: str
    name: str
    description: str
    category: TemplateCategory
    template_type: TemplateType
    content: str
    variables: List[str]
    examples: List[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    created_by: Optional[str] = None
    is_active: bool = True
    version: str = "1.0"
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.examples is None:
            self.examples = []


class DomainConfig:
    """领域配置 - 会议场景专属配置"""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._defaults = {
            # 会议场景配置
            "meeting": {
                "default_duration": 60,  # 默认会议时长(分钟)
                "max_participants": 20,
                "default_timezone": "Asia/Shanghai",
                "workdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "work_hours": {"start": "09:00", "end": "18:00"},
            },
            # 摘要配置
            "summary": {
                "max_length": 1000,
                "include_action_items": True,
                "include_decisions": True,
                "include_controversies": True,
                "include_key_points": True,
            },
            # 待办配置
            "action_item": {
                "default_priority": "medium",
                "default_due_days": 7,
                "reminder_enabled": True,
                "reminder_days_before": 2,
            },
            # 决策配置
            "decision": {
                "require_rationale": True,
                "require_owner": True,
                "require_deadline": True,
            },
            # 争议配置
            "controversy": {
                "min_confidence": 0.7,
                "auto_escalate": True,
            },
        }
    
    def load_defaults(self):
        """加载默认配置"""
        self._config = json.loads(json.dumps(self._defaults))
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点路径访问"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置值，支持点路径访问"""
        keys = key.split('.')
        config = self._config
        
        for i, k in enumerate(keys[:-1]):
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        return True
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config
    
    def update(self, config: Dict[str, Any]):
        """批量更新配置"""
        self._config.update(config)
    
    def reset_to_defaults(self):
        """重置为默认配置"""
        self.load_defaults()


class PromptMarket:
    """Prompt模板市场"""
    
    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._domain_config = DomainConfig()
        self._load_default_templates()
    
    def _load_default_templates(self):
        """加载默认模板"""
        default_templates = [
            PromptTemplate(
                template_id="meeting_summary_v1",
                name="会议总结模板",
                description="用于生成会议总结的标准模板",
                category=TemplateCategory.MEETING_SUMMARY,
                template_type=TemplateType.SYSTEM,
                content="""你是一位专业的会议记录员。请根据以下会议内容，生成一份详细的会议总结：

会议基本信息：
- 会议主题：{meeting_topic}
- 会议时间：{meeting_time}
- 参会人员：{participants}

会议内容：
{meeting_content}

请按照以下结构输出总结：
1. 会议概述
2. 讨论要点
3. 达成的决策
4. 待办事项
5. 下次会议安排

要求：
- 语言简洁明了
- 重点突出
- 不超过{max_length}字
""",
                variables=["meeting_topic", "meeting_time", "participants", "meeting_content", "max_length"],
                examples=[
                    "会议主题：Q3产品规划讨论\n会议时间：2024-01-15 14:00-15:30\n参会人员：张三、李四、王五\n会议内容：讨论了Q3产品路线图..."
                ]
            ),
            PromptTemplate(
                template_id="action_item_v1",
                name="待办事项提取模板",
                description="从会议内容中提取待办事项",
                category=TemplateCategory.ACTION_ITEM,
                template_type=TemplateType.SYSTEM,
                content="""请从以下会议内容中提取待办事项：

会议内容：
{meeting_content}

待办事项格式要求：
- 每项待办包含：负责人、任务描述、截止日期
- 按优先级排序（高、中、低）
- 用中文输出

输出格式：
【高优先级】
- [负责人] 任务描述（截止日期）
【中优先级】
- [负责人] 任务描述（截止日期）
【低优先级】
- [负责人] 任务描述（截止日期）
""",
                variables=["meeting_content"],
                examples=[
                    "张三负责完成产品原型设计，下周五之前完成。李四跟进技术方案评审..."
                ]
            ),
            PromptTemplate(
                template_id="decision_record_v1",
                name="决策记录模板",
                description="记录会议决策",
                category=TemplateCategory.DECISION_RECORD,
                template_type=TemplateType.SYSTEM,
                content="""请从以下会议内容中识别并记录决策：

会议内容：
{meeting_content}

决策记录格式：
1. 决策事项：
2. 决策内容：
3. 决策依据：
4. 负责人：
5. 执行期限：
6. 后续跟进：

要求：
- 每条决策单独记录
- 明确责任人和时间节点
""",
                variables=["meeting_content"],
                examples=[
                    "会议决定采用方案A作为技术架构方案..."
                ]
            ),
            PromptTemplate(
                template_id="controversy_analysis_v1",
                name="争议分析模板",
                description="分析会议中的争议点",
                category=TemplateCategory.CONTROVERSY,
                template_type=TemplateType.SYSTEM,
                content="""请分析以下会议内容中的争议点：

会议内容：
{meeting_content}

争议分析要求：
1. 识别争议话题
2. 各方观点
3. 争议焦点
4. 建议解决方案

输出格式：
【争议话题】
- 话题描述

【各方观点】
- [方1]: 观点内容
- [方2]: 观点内容

【争议焦点】
- 焦点描述

【建议方案】
- 方案描述
""",
                variables=["meeting_content"],
                examples=[
                    "关于技术选型存在分歧，一方建议使用方案A，另一方建议使用方案B..."
                ]
            ),
            PromptTemplate(
                template_id="qa_analysis_v1",
                name="问答分析模板",
                description="基于会议内容回答问题",
                category=TemplateCategory.QA_ANALYSIS,
                template_type=TemplateType.SYSTEM,
                content="""请根据以下会议内容回答问题：

会议内容：
{meeting_context}

问题：
{question}

要求：
- 基于提供的会议内容回答
- 如果答案不在会议内容中，请说明"会议内容中未提及"
- 引用来源格式：[文档ID:chunk_index]
- 语言简洁准确
""",
                variables=["meeting_context", "question"],
                examples=[
                    "会议内容：张三提出了新的产品方案...\n问题：谁提出了新的产品方案？\n回答：张三[文档1:0]"
                ]
            ),
            PromptTemplate(
                template_id="meeting_plan_v1",
                name="会议规划模板",
                description="规划会议议程",
                category=TemplateCategory.MEETING_PLAN,
                template_type=TemplateType.SYSTEM,
                content="""请为以下会议主题规划议程：

会议主题：{meeting_topic}
预计时长：{duration}分钟
参会人员：{participants}

议程规划要求：
1. 开场介绍（5分钟）
2. 主要议题讨论
3. 总结与行动项
4. 下次会议安排

输出格式：
【会议议程】
时间点 - 议题 - 负责人 - 时长

示例：
00:00-00:05 - 开场介绍 - 主持人 - 5分钟
00:05-00:20 - 议题1讨论 - 张三 - 15分钟
...
""",
                variables=["meeting_topic", "duration", "participants"],
                examples=[
                    "会议主题：Q3产品规划\n预计时长：90分钟\n参会人员：产品、研发、设计团队"
                ]
            ),
            PromptTemplate(
                template_id="follow_up_v1",
                name="跟进提醒模板",
                description="生成跟进提醒内容",
                category=TemplateCategory.FOLLOW_UP,
                template_type=TemplateType.SYSTEM,
                content="""请根据以下待办事项生成跟进提醒：

待办事项：
{action_items}

当前日期：{current_date}

跟进提醒要求：
- 语气友好
- 明确任务和截止日期
- 提醒即将到期的任务

输出格式：
【跟进提醒】

尊敬的各位同事：

以下是需要跟进的事项：

1. [任务描述] - 负责人：[姓名]，截止日期：[日期]

请各位及时推进相关工作，如有问题请及时沟通。

谢谢！
""",
                variables=["action_items", "current_date"],
                examples=[
                    "待办事项：张三负责完成产品原型设计，截止日期：2024-01-20"
                ]
            ),
        ]
        
        for template in default_templates:
            self._templates[template.template_id] = template
            app_logger.info(f"[PromptMarket] 加载默认模板: {template.name}")
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self._templates.get(template_id)
    
    def get_templates_by_category(self, category: TemplateCategory) -> List[PromptTemplate]:
        """按分类获取模板"""
        return [t for t in self._templates.values() if t.category == category and t.is_active]
    
    def get_all_templates(self) -> List[Dict[str, Any]]:
        """获取所有模板"""
        result = []
        for template in self._templates.values():
            data = asdict(template)
            data["created_at"] = template.created_at.isoformat()
            data["updated_at"] = template.updated_at.isoformat()
            result.append(data)
        return result
    
    def create_template(self, **kwargs) -> PromptTemplate:
        """创建模板"""
        template = PromptTemplate(
            template_id=f"template_{int(datetime.now().timestamp())}",
            **kwargs
        )
        self._templates[template.template_id] = template
        app_logger.info(f"[PromptMarket] 创建模板: {template.name}")
        return template
    
    def update_template(self, template_id: str, **kwargs) -> bool:
        """更新模板"""
        if template_id not in self._templates:
            return False
        
        template = self._templates[template_id]
        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        template.updated_at = datetime.now()
        app_logger.info(f"[PromptMarket] 更新模板: {template.name}")
        return True
    
    def delete_template(self, template_id: str) -> bool:
        """删除模板"""
        if template_id not in self._templates:
            return False
        
        template = self._templates.pop(template_id)
        app_logger.info(f"[PromptMarket] 删除模板: {template.name}")
        return True
    
    def get_domain_config(self) -> DomainConfig:
        """获取领域配置"""
        return self._domain_config
    
    def render_template(self, template_id: str, **variables) -> Optional[str]:
        """渲染模板"""
        template = self.get_template(template_id)
        if not template:
            return None
        
        try:
            return template.content.format(**variables)
        except KeyError as e:
            app_logger.error(f"[PromptMarket] 模板渲染失败，缺少变量: {e}")
            return None


# 全局实例
prompt_market = PromptMarket()


def get_prompt_market() -> PromptMarket:
    """获取Prompt模板市场实例"""
    return prompt_market
