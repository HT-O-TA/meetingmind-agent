"""Prompt 模板系统 - 集中管理系统中所有 Prompt 模板

优化要点：
1. 语言精炼：去除冗余表述，增强指令明确性
2. 结构化输出：强制JSON格式，定义输出schema
3. 示例数据：添加few-shot示例提升LLM输出质量
4. 验证机制：实现JSON schema验证
"""
import json
import jsonschema
from typing import Dict, List, Optional, Any, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum


class PromptType(Enum):
    """Prompt 类型枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class OutputFormat(Enum):
    """输出格式枚举"""
    JSON = "json"
    TEXT = "text"
    MARKDOWN = "markdown"


@dataclass
class OutputSchema:
    """输出JSON Schema定义"""
    schema: Dict[str, Any]
    example: Optional[Dict[str, Any]] = None

    def validate(self, output: str) -> bool:
        """验证输出是否符合schema"""
        try:
            data = json.loads(output)
            jsonschema.validate(data, self.schema)
            return True
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return False


@dataclass
class PromptExample:
    """Prompt示例数据"""
    input: Dict[str, str]
    output: str


@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""
    name: str
    template: str
    type: PromptType
    description: str = ""
    variables: List[str] = field(default_factory=list)
    examples: List[PromptExample] = field(default_factory=list)
    output_format: OutputFormat = OutputFormat.JSON
    output_schema: Optional[OutputSchema] = None
    requirements: List[str] = field(default_factory=list)
    created_at: str = ""

    def render(self, **kwargs) -> str:
        """渲染 Prompt 模板，包含示例数据"""
        try:
            # 构建完整的模板内容
            content = self.template.format(**kwargs)
            
            # 如果有示例，添加few-shot部分
            if self.examples:
                examples_section = "\n\n【示例】\n"
                for i, example in enumerate(self.examples, 1):
                    examples_section += f"示例{i}:\n输入:\n"
                    for key, value in example.input.items():
                        examples_section += f"- {key}: {value}\n"
                    examples_section += f"输出:\n{example.output}\n\n"
                content += examples_section
            
            # 添加输出格式要求
            if self.output_format == OutputFormat.JSON and self.output_schema:
                schema_str = json.dumps(self.output_schema.schema, ensure_ascii=False, indent=2)
                content += f"\n\n【输出格式要求】\n必须输出严格符合以下JSON Schema的内容:\n{schema_str}"
            
            return content
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

    def validate_output(self, output: str) -> bool:
        """验证输出是否符合定义的格式"""
        if self.output_format == OutputFormat.JSON:
            return self.output_schema.validate(output) if self.output_schema else False
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
                description="Agent 规划阶段 Prompt - 分析问题并生成执行计划",
                template=(
                    "你是任务规划专家。分析问题，决定调用工具完成任务。\n\n"
                    "工具信息:\n{tools_info}\n\n"
                    "问题: {question}\n"
                    "上下文: {context}\n\n"
                    "输出执行计划JSON:"
                ),
                variables=["tools_info", "question", "context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["analysis", "tasks", "execution_order"],
                        "properties": {
                            "analysis": {"type": "string", "description": "问题分析"},
                            "tasks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["task_id", "task_type", "description"],
                                    "properties": {
                                        "task_id": {"type": "string"},
                                        "task_type": {"type": "string", "enum": ["qa", "todo", "minutes", "controversy", "search", "combine"]},
                                        "description": {"type": "string"},
                                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                                        "tool_to_use": {"type": "string"},
                                        "dependencies": {"type": "array", "items": {"type": "string"}}
                                    }
                                }
                            },
                            "tool_calls": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["tool_name", "arguments"],
                                    "properties": {
                                        "tool_name": {"type": "string"},
                                        "arguments": {"type": "object"}
                                    }
                                }
                            },
                            "execution_order": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    example={
                        "analysis": "用户需要了解会议中的待办事项",
                        "tasks": [
                            {"task_id": "task_1", "task_type": "todo", "description": "提取待办事项", "priority": 1, "tool_to_use": "extract_todos", "dependencies": []}
                        ],
                        "tool_calls": [{"tool_name": "extract_todos", "arguments": {"context": "会议内容"}}],
                        "execution_order": ["task_1"]
                    }
                ),
                examples=[
                    PromptExample(
                        input={
                            "tools_info": "工具列表: extract_todos-提取待办, generate_minutes-生成纪要",
                            "question": "会议中有哪些待办事项?",
                            "context": "会议讨论了项目进度，张三需要完成文档编写"
                        },
                        output='{"analysis":"用户需要从会议中提取待办事项","tasks":[{"task_id":"task_1","task_type":"todo","description":"提取会议待办事项","priority":1,"tool_to_use":"extract_todos","dependencies":[]}],"tool_calls":[{"tool_name":"extract_todos","arguments":{"context":"会议讨论了项目进度，张三需要完成文档编写"}}],"execution_order":["task_1"]}'
                    ),
                    PromptExample(
                        input={
                            "tools_info": "工具列表: search_meeting-搜索会议内容",
                            "question": "上次产品讨论会议的结论是什么?",
                            "context": ""
                        },
                        output='{"analysis":"用户需要搜索历史会议内容获取产品讨论结论","tasks":[{"task_id":"task_1","task_type":"search","description":"搜索产品讨论会议","priority":1,"tool_to_use":"search_meeting","dependencies":[]}],"tool_calls":[{"tool_name":"search_meeting","arguments":{"query":"产品讨论会议结论"}}],"execution_order":["task_1"]}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="agent_reflection",
                type=PromptType.USER,
                description="Agent 反思阶段 Prompt - 多维度质量评估",
                template=(
                    "从4个维度评估执行结果质量:\n\n"
                    "评估标准:\n"
                    "1. 准确性(accuracy): 回答是否准确基于事实, 0.0-1.0\n"
                    "2. 相关性(relevance): 回答是否切题解决问题, 0.0-1.0\n"
                    "3. 完整性(completeness): 回答是否全面覆盖要点, 0.0-1.0\n"
                    "4. 连贯性(coherence): 逻辑是否通顺表达清晰, 0.0-1.0\n\n"
                    "用户问题: {question}\n"
                    "执行结果:\n- 回答: {answer}\n- 纪要: {minutes}\n- 待办: {todos}\n- 争议点: {controversies}\n\n"
                    "输出JSON格式评估结果:"
                ),
                variables=["question", "answer", "minutes", "todos", "controversies"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["overall_score", "metrics", "confidence", "needs_retry"],
                        "properties": {
                            "overall_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "metrics": {
                                "type": "object",
                                "properties": {
                                    "accuracy": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "completeness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "coherence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                                }
                            },
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "issues": {"type": "array", "items": {"type": "string"}},
                            "suggestions": {"type": "array", "items": {"type": "string"}},
                            "needs_retry": {"type": "boolean"}
                        }
                    },
                    example={
                        "overall_score": 0.8,
                        "metrics": {"accuracy": 0.85, "relevance": 0.8, "completeness": 0.75, "coherence": 0.8},
                        "confidence": 0.9,
                        "issues": ["待办事项提取不够完整"],
                        "suggestions": ["增加待办事项提取的详细程度"],
                        "needs_retry": False
                    }
                ),
                examples=[
                    PromptExample(
                        input={
                            "question": "会议中有哪些待办?",
                            "answer": "张三负责文档编写",
                            "minutes": "",
                            "todos": '[{"content":"编写文档","assignee":"张三"}]',
                            "controversies": "[]"
                        },
                        output='{"overall_score":0.85,"metrics":{"accuracy":0.9,"relevance":0.9,"completeness":0.8,"coherence":0.9},"confidence":0.85,"issues":[],"suggestions":[],"needs_retry":false}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="agent_minutes",
                type=PromptType.USER,
                description="生成会议纪要",
                template=(
                    "根据会议内容生成结构化纪要:\n\n"
                    "会议内容:\n{context}\n\n"
                    "输出JSON格式纪要:"
                ),
                variables=["context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["meeting_topic", "participants", "discussion_points", "decisions", "action_items"],
                        "properties": {
                            "meeting_topic": {"type": "string"},
                            "participants": {"type": "array", "items": {"type": "string"}},
                            "discussion_points": {"type": "array", "items": {"type": "string"}},
                            "decisions": {"type": "array", "items": {"type": "string"}},
                            "action_items": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    example={
                        "meeting_topic": "项目进度评审",
                        "participants": ["张三", "李四"],
                        "discussion_points": ["讨论了Q3目标完成情况"],
                        "decisions": ["同意延长项目周期"],
                        "action_items": ["张三负责编写延期报告"]
                    }
                ),
                examples=[
                    PromptExample(
                        input={"context": "会议主题：产品需求评审。参会人员：张三、李四。讨论内容：新功能优先级。决议：优先开发用户管理模块。"},
                        output='{"meeting_topic":"产品需求评审","participants":["张三","李四"],"discussion_points":["新功能优先级讨论"],"decisions":["优先开发用户管理模块"],"action_items":[]}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="extract_todos",
                type=PromptType.USER,
                description="抽取待办事项",
                template=(
                    "从会议内容中抽取待办事项:\n\n"
                    "会议内容:\n{context}\n\n"
                    "输出JSON数组格式待办列表:"
                ),
                variables=["context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["content"],
                            "properties": {
                                "content": {"type": "string"},
                                "assignee": {"type": "string"},
                                "deadline": {"type": "string"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                            }
                        }
                    },
                    example=[{"content": "完成文档编写", "assignee": "张三", "deadline": "2024-01-15", "priority": "high"}]
                ),
                examples=[
                    PromptExample(
                        input={"context": "张三需要在本周五前完成技术文档编写，李四协助审核。"},
                        output='[{"content":"完成技术文档编写","assignee":"张三","deadline":"本周五","priority":"high"},{"content":"审核技术文档","assignee":"李四","deadline":"本周五","priority":"medium"}]'
                    ),
                    PromptExample(
                        input={"context": "讨论了下季度计划，没有具体任务分配。"},
                        output="[]"
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="detect_controversies",
                type=PromptType.USER,
                description="识别争议点",
                template=(
                    "从会议内容中识别争议点和分歧:\n\n"
                    "会议内容:\n{context}\n\n"
                    "输出JSON数组格式争议点列表:"
                ),
                variables=["context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["topic", "description"],
                            "properties": {
                                "topic": {"type": "string"},
                                "description": {"type": "string"},
                                "parties": {"type": "array", "items": {"type": "string"}},
                                "resolved": {"type": "boolean"}
                            }
                        }
                    },
                    example=[{"topic": "预算分配", "description": "关于营销预算分配存在分歧", "parties": ["张三", "李四"], "resolved": False}]
                ),
                examples=[
                    PromptExample(
                        input={"context": "张三认为应该增加研发预算，李四则认为应优先投入市场。双方未达成一致。"},
                        output='[{"topic":"预算分配","description":"研发预算与市场预算优先级存在分歧","parties":["张三","李四"],"resolved":false}]'
                    ),
                    PromptExample(
                        input={"context": "会议讨论顺利，所有议题达成共识。"},
                        output="[]"
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="answer_question",
                type=PromptType.USER,
                description="回答用户问题",
                template=(
                    "根据上下文回答问题:\n\n"
                    "上下文:\n{context}\n\n"
                    "问题:\n{question}\n\n"
                    "输出JSON格式回答:"
                ),
                variables=["context", "question"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["answer"],
                        "properties": {
                            "answer": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "sources": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    example={"answer": "会议定于下周一召开", "confidence": 0.95, "sources": ["会议记录2024-01-01"]}
                ),
                examples=[
                    PromptExample(
                        input={"context": "会议记录显示：产品发布时间定为2024年3月15日。", "question": "产品什么时候发布?"},
                        output='{"answer":"产品发布时间为2024年3月15日","confidence":0.95,"sources":["会议记录"]}'
                    ),
                    PromptExample(
                        input={"context": "会议讨论了多个方案，但未最终确定。", "question": "最终决定采用哪个方案?"},
                        output='{"answer":"会议中讨论了多个方案，但尚未做出最终决定。","confidence":0.8,"sources":["会议记录"]}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="system_prompt",
                type=PromptType.SYSTEM,
                description="系统 Prompt",
                template=(
                    "你是专业会议助手，提供会议纪要、待办事项、争议点识别等服务。\n"
                    "规则:\n"
                    "1. 严格按照指定JSON格式输出\n"
                    "2. 回答准确、简洁、专业\n"
                    "3. 基于提供的上下文信息回答\n"
                    "4. 无法回答时明确说明"
                ),
                variables=[],
                output_format=OutputFormat.TEXT
            )
        )

        self.register_template(
            PromptTemplate(
                name="error_recovery",
                type=PromptType.USER,
                description="错误恢复",
                template=(
                    "执行任务时发生错误:\n{error_message}\n\n"
                    "分析错误原因并重新尝试。输出修正后的执行计划JSON:"
                ),
                variables=["error_message"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["error_analysis", "retry_plan"],
                        "properties": {
                            "error_analysis": {"type": "string"},
                            "retry_plan": {"type": "object"}
                        }
                    }
                ),
                examples=[
                    PromptExample(
                        input={"error_message": "工具调用失败：缺少context参数"},
                        output='{"error_analysis":"工具调用缺少必需参数context","retry_plan":{"action":"补充context参数后重新调用","parameters":{"context":"会议内容"}}}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="context_compress",
                type=PromptType.USER,
                description="压缩上下文",
                template=(
                    "将以下内容摘要压缩，保持核心信息，不超过{max_length}字符:\n\n"
                    "{content}\n\n"
                    "输出JSON格式摘要:"
                ),
                variables=["content", "max_length"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["summary"],
                        "properties": {
                            "summary": {"type": "string"},
                            "original_length": {"type": "integer"},
                            "compressed_length": {"type": "integer"}
                        }
                    }
                ),
                examples=[
                    PromptExample(
                        input={"content": "本次会议讨论了产品开发进度，张三汇报了前端开发完成80%，李四汇报了后端API开发完成90%，数据库设计已完成。会议决定下周进行联调测试。", "max_length": "50"},
                        output='{"summary":"会议讨论进度：前端80%，后端90%，下周联调","original_length":85,"compressed_length":28}'
                    )
                ])
        )

        self.register_template(
            PromptTemplate(
                name="react_reasoning",
                type=PromptType.USER,
                description="ReAct 推理模板 - 引导 LLM 进行思考-行动-观察循环",
                template=(
                    "【任务】\n{question}\n\n"
                    "【上下文】\n{context}\n\n"
                    "【可用工具】\n{tools_info}\n\n"
                    "【历史记录】\n{history}\n\n"
                    "请按照 ReAct 格式思考：分析当前状态 → 决定行动 → 执行 → 观察结果。\n"
                    "输出JSON格式，包含thought、action、tool_name、arguments、confidence。"
                ),
                variables=["tools_info", "question", "context", "history"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["thought", "action"],
                        "properties": {
                            "thought": {"type": "string", "description": "思考过程"},
                            "action": {"type": "string", "enum": ["tool_call", "finish", "retry"]},
                            "tool_name": {"type": "string"},
                            "arguments": {"type": "object"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                        }
                    },
                    example={
                        "thought": "用户想了解会议待办，需要先搜索相关会议内容",
                        "action": "tool_call",
                        "tool_name": "search_meeting",
                        "arguments": {"query": "待办事项"},
                        "confidence": 0.85
                    }
                ),
                examples=[
                    PromptExample(
                        input={
                            "tools_info": "search_meeting-搜索会议内容",
                            "question": "上次会议有哪些待办?",
                            "context": "",
                            "history": "[]"
                        },
                        output='{"thought":"用户想了解上次会议的待办事项，首先需要搜索相关会议内容","action":"tool_call","tool_name":"search_meeting","arguments":{"query":"会议待办事项"},"confidence":0.9}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="cot_reasoning",
                type=PromptType.USER,
                description="CoT 思维链推理模板 - 引导 LLM 进行详细的链式推理",
                template=(
                    "【问题】\n{question}\n\n"
                    "【上下文】\n{context}\n\n"
                    "请逐步分析问题，输出推理步骤和最终答案。\n"
                    "输出JSON格式，包含reasoning_steps数组和final_answer。"
                ),
                variables=["question", "context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["reasoning_steps", "final_answer"],
                        "properties": {
                            "reasoning_steps": {"type": "array", "items": {"type": "string"}},
                            "final_answer": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "key_factors": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    example={
                        "reasoning_steps": [
                            "用户问产品发布时间",
                            "从上下文找到发布日期是2024年3月15日",
                            "确认信息来源可靠",
                            "整理成简洁回答"
                        ],
                        "final_answer": "产品发布时间为2024年3月15日",
                        "confidence": 0.95,
                        "key_factors": ["会议记录"]
                    }
                ),
                examples=[
                    PromptExample(
                        input={"question": "产品什么时候发布?", "context": "会议记录显示：产品发布时间定为2024年3月15日。"},
                        output='{"reasoning_steps":["用户询问产品发布时间","从会议记录中查找相关信息","找到明确日期：2024年3月15日","确认信息准确"],"final_answer":"产品发布时间为2024年3月15日","confidence":0.95,"key_factors":["会议记录"]}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="self_reflection",
                type=PromptType.USER,
                description="自我反思模板 - 让 LLM 反思自己的推理过程",
                template=(
                    "请回顾你的推理过程，进行自我反思：\n\n"
                    "【原始问题】\n{question}\n\n"
                    "【你的回答】\n{answer}\n\n"
                    "【可用上下文】\n{context}\n\n"
                    "请从以下维度评估你的回答：\n"
                    "1. 准确性：回答是否基于事实？\n"
                    "2. 完整性：是否覆盖了问题的所有方面？\n"
                    "3. 逻辑性：推理过程是否严谨？\n"
                    "4. 相关性：回答是否切题？\n\n"
                    "输出你的反思结果:"
                ),
                variables=["question", "answer", "context"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["assessment", "suggestions"],
                        "properties": {
                            "assessment": {
                                "type": "object",
                                "properties": {
                                    "accuracy": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "completeness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "logicality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                                }
                            },
                            "suggestions": {"type": "array", "items": {"type": "string"}},
                            "needs_revision": {"type": "boolean"},
                            "revision_plan": {"type": "string"}
                        }
                    }
                ),
                examples=[
                    PromptExample(
                        input={"question": "产品什么时候发布?", "answer": "产品将在2024年发布", "context": "会议记录：产品发布时间定为2024年3月15日。"},
                        output='{"assessment":{"accuracy":0.7,"completeness":0.5,"logicality":0.8,"relevance":1.0},"suggestions":["回答不够具体，应该给出确切日期"],"needs_revision":true,"revision_plan":"补充具体的发布日期"}'
                    )
                ]
            )
        )

        self.register_template(
            PromptTemplate(
                name="plan_refinement",
                type=PromptType.USER,
                description="计划优化模板 - 基于反馈迭代优化执行计划",
                template=(
                    "根据执行结果和反思，优化你的执行计划：\n\n"
                    "【原始问题】\n{question}\n\n"
                    "【上次计划】\n{previous_plan}\n\n"
                    "【执行结果】\n{execution_result}\n\n"
                    "【反思反馈】\n{reflection}\n\n"
                    "请分析问题所在，制定优化后的执行计划："
                ),
                variables=["question", "previous_plan", "execution_result", "reflection"],
                output_format=OutputFormat.JSON,
                output_schema=OutputSchema(
                    schema={
                        "type": "object",
                        "required": ["analysis", "revised_plan"],
                        "properties": {
                            "analysis": {"type": "string"},
                            "revised_plan": {
                                "type": "object",
                                "properties": {
                                    "tasks": {"type": "array"},
                                    "execution_order": {"type": "array", "items": {"type": "string"}},
                                    "tool_calls": {"type": "array"}
                                }
                            },
                            "changes": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                )
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
                "output_format": tmpl.output_format.value,
                "variables": tmpl.variables,
                "has_examples": len(tmpl.examples) > 0,
                "has_schema": tmpl.output_schema is not None
            }
            for name, tmpl in self.templates.items()
        ]

    def validate_output(self, template_name: str, output: str) -> bool:
        """验证输出是否符合模板定义的格式"""
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Prompt 模板 '{template_name}' 不存在")
        return template.validate_output(output)
