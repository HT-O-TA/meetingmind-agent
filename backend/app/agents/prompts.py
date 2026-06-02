"""Prompt 模板系统 - 集中管理系统中所有 Prompt 模板
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class PromptType(Enum):
    """Prompt 类型枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""
    name: str
    template: str
    type: PromptType
    description: str = ""
    variables: List[str] = field(default_factory=list)
    examples: List[Dict[str, str]] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    created_at: str = ""

    def render(self, **kwargs) -> str:
        """渲染 Prompt 模板"""
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            missing = [k for k in self.variables if k not in kwargs]
            missing_str = ", ".join(missing) if missing else str(e)
            raise ValueError(f"缺少必要模板变量: {missing_str}")

    def validate(self, **kwargs) -> bool:
        """验证模板变量是否完整"""
        for var in self.variables:
            if var not in kwargs:
                return False
        return True


class PromptManager:
    """Prompt 管理器 - 集中管理所有模板"""

    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self._register_default_templates()

    def _register_default_templates(self):
        """注册默认模板"""
        self.register_template(
            PromptTemplate(
                name="agent_plan",
                type=PromptType.USER,
                description="Agent 规划阶段 Prompt",
                template=(
                    "你是一个任务规划专家，同时负责决定使用哪些工具。\n\n{tools_info}\n\n"
                    "请分析以下问题，决定需要调用哪些工具来完成任务：\n\n"
                    "问题：{question}\n\n上下文：{context}\n\n"
                    "请按以下格式输出执行计划：\n"
                    '{{\n    "analysis": "问题分析",\n'
                    '    "tasks": [\n        {{\n'
                    '            "task_id": "task_1",\n'
                    '            "task_type": "qa/todo/minutes/controversy",\n'
                    '            "description": "任务描述",\n'
                    '            "priority": 1,\n'
                    '            "tool_to_use": "使用的工具名（可选）"\n'
                    "        }}\n    ],\n"
                    '    "tool_calls": [\n        {{\n'
                    '            "tool_name": "工具名",\n'
                    '            "arguments": {{"参数名": "参数值"}}\n'
                    "        }}\n    ],\n"
                    '    "execution_order": ["task_1", ...]\n}}'
                ),
                variables=["tools_info", "question", "context"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="agent_reflection",
                type=PromptType.USER,
                description="Agent 反思阶段 Prompt",
                template=(
                    "请评估 Agent 执行结果的质量：\n\n"
                    "用户问题：{question}\n\n执行结果：\n"
                    "- 回答：{answer}\n- 纪要：{minutes}\n"
                    "- 待办：{todos}\n- 争议点：{controversies}\n\n"
                    '请输出 JSON：\n{{\n    "quality_score": 0.8,\n'
                    '    "issues": ["问题列表"],\n'
                    '    "suggestions": ["改进建议"],\n'
                    '    "needs_retry": false\n}}'
                ),
                variables=["question", "answer", "minutes", "todos", "controversies"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="agent_minutes",
                type=PromptType.USER,
                description="生成会议纪要",
                template="请生成会议纪要：{context}",
                variables=["context"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="extract_todos",
                type=PromptType.USER,
                description="抽取待办事项",
                template="从以下会议内容中抽取待办事项：\n{context}\n\n请输出 JSON 数组格式的待办事项列表。",
                variables=["context"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="detect_controversies",
                type=PromptType.USER,
                description="识别争议点",
                template="从以下会议内容中识别争议点和分歧：\n{context}",
                variables=["context"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="answer_question",
                type=PromptType.USER,
                description="回答用户问题",
                template="根据以下上下文回答用户问题：\n\n上下文：{context}\n\n问题：{question}",
                variables=["context", "question"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="system_prompt",
                type=PromptType.SYSTEM,
                description="系统 Prompt",
                template="你是一个专业的会议助手，提供会议纪要、待办事项、争议点识别等服务。请准确、简洁地完成用户的请求。",
                variables=[]
            )
        )

        self.register_template(
            PromptTemplate(
                name="error_recovery",
                type=PromptType.USER,
                description="错误恢复时使用的 Prompt",
                template="之前尝试执行任务时发生错误：\n{error_message}\n\n请重新尝试，避免同样的错误。",
                variables=["error_message"]
            )
        )

        self.register_template(
            PromptTemplate(
                name="context_compress",
                type=PromptType.USER,
                description="压缩上下文",
                template="请将以下内容进行摘要，保持核心信息，不要超过 {max_length}个字符：\n\n{content}",
                variables=["content", "max_length"]
            )
        )

    def register_template(self, template: PromptTemplate):
        """注册模板"""
        self.templates[template.name] = template

    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self.templates.get(name)

    def render_prompt(self, name: str, **kwargs) -> str:
        """渲染指定模板"""
        template = self.get_template(name)
        if not template:
            raise ValueError(f"Prompt 模板 '{name}' 不存在")
        return template.render(**kwargs)

    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板"""
        return [
            {
                "name": name,
                "description": tmpl.description,
                "type": tmpl.type.value,
                "variables": tmpl.variables
            }
            for name, tmpl in self.templates.items()
        ]
