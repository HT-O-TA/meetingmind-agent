"""风险规则服务 - 可配置风险规则管理

功能：
1. 从数据库加载风险规则，内存缓存
2. 支持热加载（清除缓存后重新加载）
3. 支持按租户隔离
4. 支持关键词/正则/精确匹配
5. 降级兜底：数据库不可用时使用硬编码规则
"""
import re
import time
from typing import Optional, List, Dict, Tuple, Any
from app.core.logger import app_logger


# 硬编码兜底规则（数据库不可用时使用）
FALLBACK_RULES = [
    {
        "name": "删除类",
        "keywords": ["删除", "移除", "清空", "作废", "delete", "remove", "clear", "drop"],
        "level": "CRITICAL",
        "match_mode": "contains",
        "priority": 100,
    },
    {
        "name": "写入类",
        "keywords": ["创建", "新增", "更新", "修改", "保存", "提交", "批量", "写入",
                      "create", "update", "save", "submit", "bulk", "insert"],
        "level": "HIGH",
        "match_mode": "contains",
        "priority": 90,
    },
    {
        "name": "导出类",
        "keywords": ["导出", "下载", "export", "download"],
        "level": "MEDIUM",
        "match_mode": "contains",
        "priority": 80,
    },
    {
        "name": "分享类",
        "keywords": ["分享", "共享", "share", "publish"],
        "level": "MEDIUM",
        "match_mode": "contains",
        "priority": 70,
    },
]


class RiskRuleService:
    """风险规则服务"""

    def __init__(self):
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 缓存有效期 5 分钟
        self._use_fallback: bool = False
        self._fallback_rules: List[Dict[str, Any]] = FALLBACK_RULES.copy()

    def reload(self) -> None:
        """强制刷新缓存"""
        self._cache = None
        self._cache_time = 0
        app_logger.info("[RiskRuleService] 缓存已刷新，下次访问将重新加载")

    def get_rules(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取风险规则列表（按优先级排序）"""
        rules = self._load_rules()

        if tenant_id:
            # 过滤租户规则 + 全局规则
            rules = [r for r in rules if not r.get("tenant_id") or r.get("tenant_id") == tenant_id]

        # 按优先级降序排列
        rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
        return rules

    def evaluate_risk(
        self,
        question: str,
        tenant_id: Optional[str] = None,
    ) -> Tuple[str, bool, str]:
        """评估问题的风险等级

        Returns:
            (risk_level, requires_confirmation, reason)
        """
        if not question or not question.strip():
            return "LOW", False, "空输入"

        normalized = question.lower()
        rules = self.get_rules(tenant_id)

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if self._match_rule(normalized, rule):
                level = rule.get("level", "LOW")
                requires_confirmation = level in ("HIGH", "CRITICAL")
                return level, requires_confirmation, f"匹配规则'{rule.get('name')}': {rule.get('level')}风险"

        return "LOW", False, "未命中任何风险规则"

    def _load_rules(self) -> List[Dict[str, Any]]:
        """加载规则（优先缓存，失败降级）"""
        now = time.time()

        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        try:
            rules = self._load_from_db()
            if rules:
                self._cache = rules
                self._cache_time = now
                self._use_fallback = False
                return rules
            raise ValueError("数据库返回空规则")
        except Exception as e:
            app_logger.warning(f"[RiskRuleService] 数据库加载失败，使用兜底规则: {e}")
            self._use_fallback = True
            self._cache = self._fallback_rules
            self._cache_time = now
            return self._fallback_rules

    def _load_from_db(self) -> List[Dict[str, Any]]:
        """从数据库加载规则（异步调用，这里做同步封装）"""
        try:
            from app.db.database import get_session
            from sqlalchemy import select

            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在 async 上下文中，使用 run_coroutine_threadsafe
                # 简化处理：直接返回 fallback
                raise RuntimeError("在异步上下文中，跳过同步数据库加载")

            async def _load():
                async with get_session() as session:
                    result = await session.execute(
                        select(
                            __import__("app.models.risk_rule", fromlist=["RiskRule"]).RiskRule
                        ).where(
                            __import__("app.models.risk_rule", fromlist=["RiskRule"]).RiskRule.enabled == True
                        )
                    )
                    rows = result.scalars().all()
                    return [r.to_dict() for r in rows]

            return loop.run_until_complete(_load())
        except Exception as e:
            app_logger.warning(f"[RiskRuleService] _load_from_db 失败: {e}")
            raise

    def _match_rule(self, normalized_question: str, rule: Dict[str, Any]) -> bool:
        """检查问题是否匹配规则"""
        match_mode = rule.get("match_mode", "contains")
        keywords = rule.get("keywords", [])

        if not keywords:
            return False

        if match_mode == "regex":
            # 正则匹配
            for pattern in keywords:
                try:
                    if re.search(pattern, normalized_question, re.IGNORECASE):
                        return True
                except re.error:
                    continue
        elif match_mode == "exact":
            # 精确匹配
            for keyword in keywords:
                if keyword.lower() == normalized_question.strip():
                    return True
        else:
            # contains 模式（默认）
            for keyword in keywords:
                if keyword.lower() in normalized_question:
                    return True

        return False

    def is_using_fallback(self) -> bool:
        """当前是否使用兜底规则"""
        return self._use_fallback

    def add_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """添加规则（写入数据库并刷新缓存）"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                app_logger.warning("[RiskRuleService] 在异步上下文中无法同步添加规则")
                return None

            async def _add():
                from app.db.database import get_session
                from app.models.risk_rule import RiskRule
                obj = RiskRule(**{
                    "name": rule_data.get("name", "自定义规则"),
                    "description": rule_data.get("description", ""),
                    "keywords": rule_data.get("keywords", []),
                    "level": rule_data.get("level", "MEDIUM"),
                    "enabled": rule_data.get("enabled", True),
                    "tenant_id": rule_data.get("tenant_id"),
                    "priority": rule_data.get("priority", 50),
                    "match_mode": rule_data.get("match_mode", "contains"),
                })
                async with get_session() as session:
                    session.add(obj)
                    await session.commit()
                    await session.refresh(obj)
                return obj.to_dict()

            result = loop.run_until_complete(_add())
            self.reload()
            return result
        except Exception as e:
            app_logger.error(f"[RiskRuleService] 添加规则失败: {e}")
            return None


_risk_rule_instance: Optional[RiskRuleService] = None


def get_risk_rule_service() -> RiskRuleService:
    global _risk_rule_instance
    if _risk_rule_instance is None:
        _risk_rule_instance = RiskRuleService()
    return _risk_rule_instance
