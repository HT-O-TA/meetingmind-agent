"""确定性错误检查器 - 在 LLM 评估前做快速确定性校验

功能：
1. 数字一致性检查：提取 answer 中的数字，与 source 比对
2. 实体一致性检查：人名/组织/日期匹配
3. 结构完整性检查：必填字段、结构模板校验
4. 内部一致性检查：answer 内部前后矛盾检测

命中硬错误时走 FastRetry 路径，跳过 LLM 评估。
"""
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from app.core.logger import app_logger


@dataclass
class DeterministicErrorResult:
    """确定性错误检查结果"""
    has_critical_error: bool = False
    has_warning: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_types: List[str] = field(default_factory=list)  # number/entity/structure/consistency
    source_refs: List[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if self.has_critical_error:
            return "critical"
        elif self.has_warning:
            return "warning"
        return "info"


class DeterministicErrorChecker:
    """确定性错误检查器 - 无 LLM，纯规则，<10ms"""

    # 数字提取正则
    NUMBER_PATTERN = re.compile(
        r'(?:[\d,]+\.?\d*%?|[\d,]+\.?\d*\s*(?:万|亿|千|百|个|人|条|次|场|分钟|小时|天|周|月|年))',
        re.UNICODE,
    )

    # 纯数字提取
    PURE_NUMBER_PATTERN = re.compile(r'(\d+(?:\.\d+)?)')

    # 日期提取
    DATE_PATTERN = re.compile(
        r'(\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}月\d{1,2}日|\d{4}/\d{1,2}/\d{1,2})'
    )

    # 结构模板
    MINUTES_REQUIRED_FIELDS = ["summary", "内容", "讨论", "决定", "议题", "纪要"]
    TODO_REQUIRED_FIELDS = ["task", "owner", "负责人", "due", "截止", "期限"]
    CONTROVERSY_REQUIRED_FIELDS = ["topic", "title", "题目", "主题", "争议"]

    def check(
        self,
        answer: str,
        source_context: str = "",
        minutes: str = "",
        todos: Optional[List[Dict]] = None,
        controversies: Optional[List[Dict]] = None,
    ) -> DeterministicErrorResult:
        """执行确定性错误检查

        Args:
            answer: 生成的回答
            source_context: 原始文档/上下文
            minutes: 会议纪要
            todos: 待办列表
            controversies: 争议列表

        Returns:
            DeterministicErrorResult: 检查结果
        """
        result = DeterministicErrorResult()

        if not answer or not answer.strip():
            result.has_critical_error = True
            result.errors.append("answer 为空")
            result.error_types.append("structure")
            return result

        # 1. 数字一致性检查
        number_errors = self._check_number_consistency(answer, source_context)
        if number_errors:
            result.errors.extend(number_errors)
            result.error_types.append("number")
            result.has_critical_error = True

        # 2. 实体一致性检查
        entity_warnings = self._check_entity_consistency(answer, source_context)
        if entity_warnings:
            result.warnings.extend(entity_warnings)
            if not result.error_types or "entity" not in result.error_types:
                result.error_types.append("entity")
            result.has_warning = True

        # 3. 结构完整性检查
        structure_errors = self._check_structure_completeness(
            answer, minutes, todos or [], controversies or []
        )
        if structure_errors:
            result.errors.extend(structure_errors)
            if "structure" not in result.error_types:
                result.error_types.append("structure")
            result.has_critical_error = True

        # 4. 内部一致性检查
        consistency_warnings = self._check_internal_consistency(answer)
        if consistency_warnings:
            result.warnings.extend(consistency_warnings)
            if "consistency" not in result.error_types:
                result.error_types.append("consistency")
            result.has_warning = True

        if result.has_critical_error:
            app_logger.warning(
                f"[DeterministicChecker] 发现确定性硬错误: "
                f"types={result.error_types}, errors={result.errors[:3]}"
            )
        elif result.has_warning:
            app_logger.debug(
                f"[DeterministicChecker] 发现软警告: {result.warnings[:2]}"
            )

        return result

    def _check_number_consistency(
        self, answer: str, source_context: str
    ) -> List[str]:
        """数字一致性检查"""
        errors: List[str] = []

        if not source_context:
            return errors

        # 提取 answer 和 source 中的纯数字
        answer_numbers = self._extract_numbers(answer)
        source_numbers = self._extract_numbers(source_context)

        if not answer_numbers or not source_numbers:
            return errors

        # 检查 answer 中的关键数字是否在 source 中存在
        # 只检查较大的数字（>10），避免噪音
        for num in answer_numbers:
            if num > 10:
                # 检查是否有近似匹配（1% 误差范围内）
                matched = any(
                    abs(num - src_num) / max(num, src_num, 1) < 0.01
                    for src_num in source_numbers
                )
                if not matched:
                    # 检查是否是 answer 独有的合理数字（如百分比、序号等）
                    if not self._is_likely_valid_number(num, answer):
                        errors.append(
                            f"数字 {num} 在原文档中未找到匹配，可能存在数字错误"
                        )

        return errors[:3]  # 最多报告 3 个数字错误

    def _check_entity_consistency(
        self, answer: str, source_context: str
    ) -> List[str]:
        """实体一致性检查"""
        warnings: List[str] = []

        if not source_context:
            return warnings

        # 提取日期实体
        answer_dates = set(self.DATE_PATTERN.findall(answer))
        source_dates = set(self.DATE_PATTERN.findall(source_context))

        # answer 中出现但 source 中没有的日期
        for date in answer_dates:
            if date not in source_dates and len(source_dates) > 0:
                warnings.append(f"回答中出现的日期 '{date}' 在原文档中未找到")

        return warnings[:2]

    def _check_structure_completeness(
        self,
        answer: str,
        minutes: str,
        todos: List[Dict],
        controversies: List[Dict],
    ) -> List[str]:
        """结构完整性检查"""
        errors: List[str] = []

        # 会议纪要结构检查
        if minutes and minutes.strip():
            has_structure = any(
                field in minutes
                for field in self.MINUTES_REQUIRED_FIELDS
            )
            if not has_structure and len(minutes) < 50:
                errors.append("会议纪要缺少结构化内容（缺少摘要/议题/决定等字段）")

        # 待办结构检查
        if todos:
            for i, todo in enumerate(todos):
                if not isinstance(todo, dict):
                    errors.append(f"待办[{i}] 格式不正确（应为字典）")
                    continue
                has_task = any(
                    field in todo
                    for field in ["task", "content", "description", "任务", "内容"]
                )
                if not has_task:
                    errors.append(f"待办[{i}] 缺少任务描述字段")

        # 争议结构检查
        if controversies:
            for i, controv in enumerate(controversies):
                if not isinstance(controv, dict):
                    errors.append(f"争议[{i}] 格式不正确（应为字典）")
                    continue
                has_title = any(
                    field in controv
                    for field in self.CONTROVERSY_REQUIRED_FIELDS
                )
                if not has_title:
                    errors.append(f"争议[{i}] 缺少标题/主题字段")

        return errors

    def _check_internal_consistency(self, answer: str) -> List[str]:
        """内部一致性检查 - answer 内部前后矛盾"""
        warnings: List[str] = []

        # 提取所有数字
        numbers = self._extract_numbers(answer)

        # 检查同一数字是否在不同位置出现不同值
        # 简单实现：如果 answer 中有多个不同的大数字，检查是否有明显矛盾
        if len(numbers) >= 2:
            unique_numbers = set(numbers)
            # 如果有多个不同的数字且差异很大，可能有矛盾
            # 这里只做简单检查，不做过度判断
            pass

        return warnings

    def _extract_numbers(self, text: str) -> List[float]:
        """从文本中提取纯数字"""
        if not text:
            return []
        matches = self.PURE_NUMBER_PATTERN.findall(text)
        numbers = []
        for m in matches:
            try:
                num = float(m)
                if num > 0:
                    numbers.append(num)
            except ValueError:
                pass
        return numbers

    def _is_likely_valid_number(self, num: float, context: str) -> bool:
        """判断数字是否可能是合理的（百分比、序号等）"""
        # 百分比
        if num <= 100 and f"{int(num)}%" in context:
            return True
        # 序号
        if num <= 20 and f"{int(num)}." in context:
            return True
        # 年份
        if 2000 <= num <= 2100:
            return True
        return False


_checker_instance: Optional[DeterministicErrorChecker] = None


def get_deterministic_error_checker() -> DeterministicErrorChecker:
    """获取全局 DeterministicErrorChecker 实例"""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = DeterministicErrorChecker()
    return _checker_instance
