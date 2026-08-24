"""内容安全检测服务 - 多模态输入的安全防护

功能：
1. 检测恶意文件（可执行脚本、病毒特征）
2. 检测敏感内容（隐私信息、密码）
3. 返回安全等级和处理建议
"""
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from app.core.logger import app_logger


class SafetyLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"     # 有风险但可继续
    BLOCK = "block"         # 必须阻止


@dataclass
class SafetyCheckResult:
    safe: bool
    level: SafetyLevel
    reason: str = ""
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class ContentSafetyService:
    """内容安全检测服务"""

    # 敏感关键词
    SENSITIVE_KEYWORDS = [
        "密码", "password", "secret", "密钥", "key",
        "银行卡", "bank_card", "身份证", "id_card",
        "ssn", "social security", "credit_card",
    ]

    # 恶意文件特征
    MALICIOUS_PATTERNS = [
        re.compile(r'<script[^>]*>', re.IGNORECASE),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'eval\s*\(', re.IGNORECASE),
        re.compile(r'exec\s*\(', re.IGNORECASE),
        re.compile(r'\.exe\b', re.IGNORECASE),
        re.compile(r'\.bat\b', re.IGNORECASE),
        re.compile(r'\.cmd\b', re.IGNORECASE),
        re.compile(r'\.ps1\b', re.IGNORECASE),
        re.compile(r'VBScript', re.IGNORECASE),
        re.compile(r'ActiveX', re.IGNORECASE),
    ]

    # 敏感信息正则
    SENSITIVE_PATTERNS = [
        # 银行卡号
        re.compile(r'\b\d{16,19}\b'),
        # 邮箱
        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        # 手机号
        re.compile(r'\b1[3-9]\d{9}\b'),
        # IP 地址
        re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    ]

    def __init__(self):
        self._last_check_time: float = 0
        self._check_count: int = 0

    async def check_file(
        self,
        content: bytes,
        media_type: str,
    ) -> SafetyCheckResult:
        """检测文件安全性"""
        start_time = time.time()

        try:
            text_content = content.decode("utf-8", errors="ignore")
        except Exception:
            text_content = ""

        checks = []

        # 1. 恶意脚本检测
        malicious_found = self._check_malicious_patterns(text_content)
        if malicious_found:
            checks.append({
                "type": "malicious",
                "found": malicious_found,
            })

        # 2. 敏感信息检测
        sensitive_found = self._check_sensitive_info(text_content)
        if sensitive_found:
            checks.append({
                "type": "sensitive",
                "found": sensitive_found,
            })

        # 3. 关键词检测
        keyword_hits = self._check_sensitive_keywords(text_content)
        if keyword_hits:
            checks.append({
                "type": "keywords",
                "found": keyword_hits,
            })

        # 4. 大小异常检测
        size_mb = len(content) / (1024 * 1024)
        if size_mb > 100:
            checks.append({
                "type": "size",
                "message": f"文件过大 ({size_mb:.1f}MB)",
            })

        # 评估结果
        if any(c["type"] == "malicious" for c in checks):
            return SafetyCheckResult(
                safe=False,
                level=SafetyLevel.BLOCK,
                reason="检测到恶意脚本特征",
                details={"checks": checks},
            )

        if any(c["type"] == "sensitive" for c in checks):
            return SafetyCheckResult(
                safe=True,  # 敏感信息不阻止，仅记录
                level=SafetyLevel.WARNING,
                reason="检测到可能的敏感信息",
                details={"checks": checks},
            )

        self._check_count += 1
        self._last_check_time = time.time()

        return SafetyCheckResult(
            safe=True,
            level=SafetyLevel.SAFE,
            reason="安全",
            details={
                "checks": checks,
                "size_mb": round(size_mb, 2),
                "media_type": media_type,
            },
        )

    def _check_malicious_patterns(self, text: str) -> List[str]:
        """检测恶意脚本特征"""
        found = []
        for pattern in self.MALICIOUS_PATTERNS:
            if pattern.search(text):
                found.append(pattern.pattern)
        return found

    def _check_sensitive_info(self, text: str) -> List[str]:
        """检测敏感信息"""
        found = []
        for pattern in self.SENSITIVE_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                # 只记录匹配类型，不记录具体内容
                found.append(pattern.pattern[:30])
        return found

    def _check_sensitive_keywords(self, text: str) -> List[str]:
        """检测敏感关键词"""
        found = []
        text_lower = text.lower()
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword.lower() in text_lower:
                found.append(keyword)
        return found

    def check_output_text(self, text: str) -> "SafetyCheckResult":
        """检测并脱敏输出文本中的敏感信息

        对 LLM 生成的答案进行正则扫描，将命中的敏感信息替换为占位符，
        返回脱敏后的文本和安全检测结果（存放在 details["sanitized_text"]）。

        Args:
            text: LLM 生成的原始答案文本

        Returns:
            SafetyCheckResult:
              - safe=True  表示文本可以输出（已脱敏或无敏感信息）
              - level=WARNING 表示发现并脱敏了敏感信息
              - details["sanitized_text"] 为脱敏后的文本
              - details["redactions"] 为脱敏记录列表
        """
        if not text:
            return SafetyCheckResult(
                safe=True,
                level=SafetyLevel.SAFE,
                reason="空文本",
                details={"sanitized_text": text, "redactions": []},
            )

        sanitized = text
        redactions: List[str] = []

        # 手机号脱敏
        phone_pattern = re.compile(r'\b(1[3-9]\d{9})\b')
        if phone_pattern.search(sanitized):
            sanitized = phone_pattern.sub('[手机号已隐藏]', sanitized)
            redactions.append("phone_number")

        # 银行卡号脱敏（16-19位纯数字）
        card_pattern = re.compile(r'\b(\d{16,19})\b')
        if card_pattern.search(sanitized):
            sanitized = card_pattern.sub('[卡号已隐藏]', sanitized)
            redactions.append("bank_card")

        # 身份证号脱敏（18位，末位可为X）
        id_pattern = re.compile(r'\b(\d{17}[\dXx])\b')
        if id_pattern.search(sanitized):
            sanitized = id_pattern.sub('[身份证已隐藏]', sanitized)
            redactions.append("id_card")

        # 邮箱脱敏
        email_pattern = re.compile(r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b')
        if email_pattern.search(sanitized):
            sanitized = email_pattern.sub('[邮箱已隐藏]', sanitized)
            redactions.append("email")

        # 密码/密钥类明文（password= / secret= 后跟非空值）
        pwd_pattern = re.compile(
            r'(password|passwd|secret|密码|密钥|token)\s*[:=]\s*\S+',
            re.IGNORECASE,
        )
        if pwd_pattern.search(sanitized):
            sanitized = pwd_pattern.sub(r'\1=[已隐藏]', sanitized)
            redactions.append("credential")

        if redactions:
            app_logger.warning(
                f"[ContentSafety] 输出文本脱敏: {redactions}"
            )
            return SafetyCheckResult(
                safe=True,
                level=SafetyLevel.WARNING,
                reason=f"输出中检测到敏感信息并已脱敏: {redactions}",
                details={"sanitized_text": sanitized, "redactions": redactions},
            )

        return SafetyCheckResult(
            safe=True,
            level=SafetyLevel.SAFE,
            reason="输出文本安全",
            details={"sanitized_text": sanitized, "redactions": []},
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取检测统计"""
        return {
            "total_checks": self._check_count,
            "last_check_time": self._last_check_time,
        }


_safety_instance: Optional[ContentSafetyService] = None


def get_content_safety_service() -> ContentSafetyService:
    global _safety_instance
    if _safety_instance is None:
        _safety_instance = ContentSafetyService()
    return _safety_instance
