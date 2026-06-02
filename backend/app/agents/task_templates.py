"""任务模板库 - 预定义常见任务模式"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class TaskTemplateType(str, Enum):
    """任务模板类型"""
    QA = "qa"  # 问答
    SUMMARY = "summary"  # 摘要总结
    TODO_EXTRACTION = "todo_extraction"  # 待办提取
    CONTROVERSY_EXTRACTION = "controversy_extraction"  # 争议点提取
    DOCUMENT_RETRIEVAL = "document_retrieval"  # 文档检索
    MINUTES_GENERATION = "minutes_generation"  # 会议纪要生成
    MULTI_TASK = "multi_task"  # 复杂多任务

@dataclass
class SubTask:
    """子任务定义"""
    task_id: str
    task_type: str
    description: str
    priority: int = 1
    dependencies: List[str] = None  # 依赖的任务ID列表
    can_parallel_with: List[str] = None  # 可以并行的任务ID列表
    input_from: Optional[str] = None  # 从哪个任务获取输入
    output_key: Optional[str] = None  # 输出数据的键名
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.can_parallel_with is None:
            self.can_parallel_with = []

class TaskTemplate:
    """任务模板"""
    
    def __init__(
        self,
        template_id: str,
        name: str,
        template_type: TaskTemplateType,
        trigger_patterns: List[str],
        description: str,
        sub_tasks: List[SubTask],
        merge_strategy: str = "combine",
        examples: List[str] = None,
    ):
        """
        初始化任务模板
        
        Args:
            template_id: 模板ID
            name: 模板名称
            template_type: 模板类型
            trigger_patterns: 触发关键词列表
            description: 模板描述
            sub_tasks: 子任务列表
            merge_strategy: 结果合并策略 (combine/append/separate)
            examples: 示例问题
        """
        self.template_id = template_id
        self.name = name
        self.template_type = template_type
        self.trigger_patterns = trigger_patterns
        self.description = description
        self.sub_tasks = sub_tasks
        self.merge_strategy = merge_strategy
        self.examples = examples or []
    
    def match(self, question: str) -> float:
        """
        判断问题是否匹配此模板
        
        Args:
            question: 用户问题
            
        Returns:
            匹配分数 (0-1)，0表示不匹配
        """
        question_lower = question.lower()
        match_count = 0
        
        for pattern in self.trigger_patterns:
            if pattern.lower() in question_lower:
                match_count += 1
        
        if not self.trigger_patterns:
            return 0.0
        
        return match_count / len(self.trigger_patterns)
    
    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        根据模板生成任务列表
        
        Args:
            context: 上下文信息（可选）
            
        Returns:
            任务列表
        """
        tasks = []
        for sub_task in self.sub_tasks:
            task = {
                "task_id": sub_task.task_id,
                "task_type": sub_task.task_type,
                "description": sub_task.description,
                "priority": sub_task.priority,
                "status": "pending",
                "dependencies": sub_task.dependencies.copy(),
                "can_parallel_with": sub_task.can_parallel_with.copy(),
                "input_from": sub_task.input_from,
                "output_key": sub_task.output_key,
            }
            tasks.append(task)
        
        return tasks
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "type": self.template_type.value,
            "description": self.description,
            "sub_tasks": [
                {
                    "task_id": st.task_id,
                    "task_type": st.task_type,
                    "description": st.description,
                    "priority": st.priority,
                    "dependencies": st.dependencies,
                    "can_parallel_with": st.can_parallel_with,
                }
                for st in self.sub_tasks
            ],
            "merge_strategy": self.merge_strategy,
            "examples": self.examples,
        }


class TaskTemplateLibrary:
    """任务模板库"""
    
    def __init__(self):
        self.templates: List[TaskTemplate] = []
        self._load_default_templates()
    
    def _load_default_templates(self):
        """加载默认任务模板"""
        
        # 1. 简单问答模板
        self.templates.append(TaskTemplate(
            template_id="simple_qa",
            name="简单问答",
            template_type=TaskTemplateType.QA,
            trigger_patterns=["是什么", "谁", "多少", "怎么", "如何", "?"],
            description="简单的一问一答，直接从文档中提取答案",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="检索相关上下文",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="qa",
                    description="基于上下文生成回答",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
            ],
            merge_strategy="combine",
            examples=[
                "这个会议的主题是什么？",
                "谁主持了这次会议？",
            ]
        ))
        
        # 2. 会议摘要模板
        self.templates.append(TaskTemplate(
            template_id="meeting_summary",
            name="会议摘要",
            template_type=TaskTemplateType.SUMMARY,
            trigger_patterns=["总结", "摘要", "概述", "主要内容", "核心要点", "主要讨论了什么"],
            description="生成会议的整体摘要，包括主题、结论和关键点",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="获取会议完整内容",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="qa",
                    description="总结会议主题和核心内容",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
            ],
            merge_strategy="combine",
            examples=[
                "帮我总结这个会议的主要内容",
                "这个会议主要讨论了什么？",
            ]
        ))
        
        # 3. 待办提取模板
        self.templates.append(TaskTemplate(
            template_id="todo_extraction",
            name="待办事项提取",
            template_type=TaskTemplateType.TODO_EXTRACTION,
            trigger_patterns=["待办", "todo", "任务", "要做", "需要做", "action", "后续工作"],
            description="从会议中提取待办事项，包括负责人和截止时间",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="获取会议内容",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="todo",
                    description="提取待办事项",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
            ],
            merge_strategy="separate",
            examples=[
                "这个会议有哪些待办事项？",
                "会议中提到了哪些需要完成的任务？",
            ]
        ))
        
        # 4. 争议点提取模板
        self.templates.append(TaskTemplate(
            template_id="controversy_extraction",
            name="争议点提取",
            template_type=TaskTemplateType.CONTROVERSY_EXTRACTION,
            trigger_patterns=["争议", "分歧", "不同意见", "分歧点", "矛盾", "讨论点"],
            description="从会议中提取争议点，分析各方观点",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="获取会议内容",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="controversy",
                    description="识别和分析争议点",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
            ],
            merge_strategy="separate",
            examples=[
                "会议中有哪些争议点？",
                "大家对这个议题有什么不同意见？",
            ]
        ))
        
        # 5. 综合分析模板（待办+争议）
        self.templates.append(TaskTemplate(
            template_id="comprehensive_analysis",
            name="综合分析",
            template_type=TaskTemplateType.MULTI_TASK,
            trigger_patterns=["有哪些", "分析", "包含", "有哪些"],
            description="综合分析会议内容，包括待办事项和争议点",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="获取会议完整内容",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="todo",
                    description="提取待办事项",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=["task_3"],  # 与争议点并行
                    input_from="task_1",
                ),
                SubTask(
                    task_id="task_3",
                    task_type="controversy",
                    description="识别争议点",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=["task_2"],  # 与待办并行
                    input_from="task_1",
                ),
                SubTask(
                    task_id="task_4",
                    task_type="combine",
                    description="整合分析结果",
                    priority=3,
                    dependencies=["task_2", "task_3"],
                    can_parallel_with=[],
                    input_from="task_2,task_3",
                ),
            ],
            merge_strategy="combine",
            examples=[
                "这个会议有哪些待办和争议点？",
                "分析一下会议中提到的工作和分歧",
            ]
        ))
        
        # 6. 文档检索模板
        self.templates.append(TaskTemplate(
            template_id="document_retrieval",
            name="文档检索",
            template_type=TaskTemplateType.DOCUMENT_RETRIEVAL,
            trigger_patterns=["文档", "id", "哪个文档", "哪个文件", "第几个"],
            description="根据文档ID检索特定文档的内容",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="根据文档ID检索文档",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="parse",
                    description="解析文档内容",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
                SubTask(
                    task_id="task_3",
                    task_type="qa",
                    description="总结文档内容",
                    priority=3,
                    dependencies=["task_2"],
                    can_parallel_with=[],
                    input_from="task_2",
                ),
            ],
            merge_strategy="combine",
            examples=[
                "id为4的文档主要讲了哪些内容？",
                "文档50的主要内容是什么？",
            ]
        ))
        
        # 7. 会议纪要生成模板
        self.templates.append(TaskTemplate(
            template_id="minutes_generation",
            name="会议纪要生成",
            template_type=TaskTemplateType.MINUTES_GENERATION,
            trigger_patterns=["纪要", "记录", "会议记录", "会议纪要"],
            description="生成结构化的会议纪要",
            sub_tasks=[
                SubTask(
                    task_id="task_1",
                    task_type="retrieve",
                    description="获取会议内容",
                    priority=1,
                    dependencies=[],
                    can_parallel_with=[],
                ),
                SubTask(
                    task_id="task_2",
                    task_type="minutes",
                    description="生成会议纪要",
                    priority=2,
                    dependencies=["task_1"],
                    can_parallel_with=[],
                    input_from="task_1",
                ),
            ],
            merge_strategy="separate",
            examples=[
                "帮我生成会议纪要",
                "整理一下会议的主要内容",
            ]
        ))
    
    def find_best_match(self, question: str) -> Optional[TaskTemplate]:
        """
        找到最佳匹配的任务模板
        
        Args:
            question: 用户问题
            
        Returns:
            最佳匹配的模板，如果没有匹配返回None
        """
        best_match = None
        best_score = 0.0
        
        for template in self.templates:
            score = template.match(question)
            if score > best_score:
                best_score = score
                best_match = template
        
        # 设置阈值，只有分数超过阈值才返回
        if best_score >= 0.2:  # 至少匹配一个关键词
            return best_match
        
        return None
    
    def get_all_templates(self) -> List[Dict[str, Any]]:
        """获取所有模板"""
        return [t.to_dict() for t in self.templates]
    
    def get_template_by_id(self, template_id: str) -> Optional[TaskTemplate]:
        """根据ID获取模板"""
        for template in self.templates:
            if template.template_id == template_id:
                return template
        return None


# 全局模板库实例
_template_library = None

def get_task_template_library() -> TaskTemplateLibrary:
    """获取全局任务模板库实例"""
    global _template_library
    if _template_library is None:
        _template_library = TaskTemplateLibrary()
    return _template_library
