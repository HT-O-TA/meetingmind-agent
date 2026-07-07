"""AI 成本管理模块 - 模型路由、Token预算、缓存策略、成本监控"""
import time
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque

from app.core.logger import app_logger
from app.core.config import settings


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    prompt_cost_usd_per_1k: float
    completion_cost_usd_per_1k: float
    max_tokens: int
    capability: str = "general"
    description: str = ""
    
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """计算成本"""
        return (prompt_tokens / 1000) * self.prompt_cost_usd_per_1k + \
               (completion_tokens / 1000) * self.completion_cost_usd_per_1k


@dataclass
class TokenBudget:
    """Token 预算"""
    daily_limit: int
    monthly_limit: int
    daily_used: int = 0
    monthly_used: int = 0
    last_reset_date: str = ""
    last_reset_month: str = ""
    
    def check_budget(self, tokens_needed: int) -> bool:
        """检查是否有足够预算"""
        self._ensure_reset()
        return (self.daily_used + tokens_needed <= self.daily_limit) and \
               (self.monthly_used + tokens_needed <= self.monthly_limit)
    
    def consume_tokens(self, tokens: int):
        """消耗 Token"""
        self._ensure_reset()
        self.daily_used += tokens
        self.monthly_used += tokens
    
    def get_remaining(self) -> Dict[str, int]:
        """获取剩余预算"""
        self._ensure_reset()
        return {
            "daily_remaining": self.daily_limit - self.daily_used,
            "monthly_remaining": self.monthly_limit - self.monthly_used,
            "daily_used": self.daily_used,
            "monthly_used": self.monthly_used,
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit
        }
    
    def _ensure_reset(self):
        """确保预算已按周期重置"""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")
        
        if self.last_reset_date != today:
            self.daily_used = 0
            self.last_reset_date = today
        
        if self.last_reset_month != current_month:
            self.monthly_used = 0
            self.last_reset_month = current_month


@dataclass
class CostRecord:
    """成本记录"""
    timestamp: float
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    task_type: str
    success: bool = True
    error: str = None


class CostManager:
    """
    AI 成本管理器
    
    功能：
    1. 模型路由 - 根据任务复杂度选择合适的模型
    2. Token 预算管理 - 每日/每月预算限制
    3. 成本监控 - 实时跟踪成本消耗
    4. 缓存策略 - 结果缓存减少重复调用
    """
    
    def __init__(self):
        self._models = self._load_models()
        self._budget = TokenBudget(
            daily_limit=settings.COST_DAILY_TOKEN_LIMIT or 100000,
            monthly_limit=settings.COST_MONTHLY_TOKEN_LIMIT or 3000000,
            last_reset_date=datetime.now().strftime("%Y-%m-%d"),
            last_reset_month=datetime.now().strftime("%Y-%m")
        )
        self._cost_records = deque(maxlen=10000)
        self._result_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = settings.COST_CACHE_TTL or 3600
        self._total_cost_usd = 0.0
        self._total_tokens = 0
    
    def _load_models(self) -> Dict[str, ModelInfo]:
        """加载模型配置"""
        models = {
            "qwen-max": ModelInfo(
                name="qwen-max",
                prompt_cost_usd_per_1k=0.015,
                completion_cost_usd_per_1k=0.03,
                max_tokens=8192,
                capability="advanced",
                description="通义千问 Max，适合复杂推理任务"
            ),
            "qwen-plus": ModelInfo(
                name="qwen-plus",
                prompt_cost_usd_per_1k=0.003,
                completion_cost_usd_per_1k=0.006,
                max_tokens=4096,
                capability="general",
                description="通义千问 Plus，适合日常对话"
            ),
            "qwen": ModelInfo(
                name="qwen",
                prompt_cost_usd_per_1k=0.001,
                completion_cost_usd_per_1k=0.002,
                max_tokens=2048,
                capability="simple",
                description="通义千问，适合简单任务"
            ),
            "qwen-turbo": ModelInfo(
                name="qwen-turbo",
                prompt_cost_usd_per_1k=0.0008,
                completion_cost_usd_per_1k=0.0016,
                max_tokens=4096,
                capability="simple",
                description="通义千问 Turbo，极速且便宜"
            ),
        }
        
        return models
    
    def select_model(self, task_type: str, complexity: str = "medium") -> str:
        """
        根据任务类型和复杂度选择模型
        
        Args:
            task_type: 任务类型（summarization/analysis/qa/planning/reflection/simple）
            complexity: 复杂度（simple/medium/complex）
            
        Returns:
            模型名称
        """
        if complexity == "simple" or task_type == "simple":
            return "qwen-turbo"
        elif complexity == "medium" or task_type in ["qa", "summarization"]:
            return "qwen-plus"
        elif complexity == "complex" or task_type in ["analysis", "planning", "reflection"]:
            return "qwen-max"
        else:
            return settings.LLM_MODEL or "qwen-plus"
    
    def calculate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """计算调用成本"""
        model = self._models.get(model_name)
        if model:
            return model.calculate_cost(prompt_tokens, completion_tokens)
        return 0.0
    
    def check_budget(self, tokens_needed: int) -> bool:
        """检查预算是否充足"""
        return self._budget.check_budget(tokens_needed)
    
    def consume_tokens(self, tokens: int):
        """消耗 Token"""
        self._budget.consume_tokens(tokens)
        self._total_tokens += tokens
    
    def record_cost(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        task_type: str,
        success: bool = True,
        error: str = None
    ):
        """记录成本"""
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self.calculate_cost(model_name, prompt_tokens, completion_tokens)
        
        record = CostRecord(
            timestamp=time.time(),
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            task_type=task_type,
            success=success,
            error=error
        )
        
        self._cost_records.append(record)
        self._total_cost_usd += cost_usd
        self.consume_tokens(total_tokens)
    
    def get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        cached = self._result_cache.get(key)
        if cached:
            if time.time() - cached["timestamp"] < self._cache_ttl:
                return cached
            else:
                del self._result_cache[key]
        return None
    
    def set_cache(self, key: str, result: str, model_name: str, cost_usd: float):
        """设置缓存"""
        self._result_cache[key] = {
            "timestamp": time.time(),
            "result": result,
            "model_name": model_name,
            "cost_usd": cost_usd
        }
    
    def generate_cache_key(self, prompt: str, model_name: str) -> str:
        """生成缓存键"""
        return hashlib.md5(f"{prompt}:{model_name}".encode()).hexdigest()
    
    def get_cost_stats(self) -> Dict[str, Any]:
        """获取成本统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_records = [r for r in self._cost_records 
                        if datetime.fromtimestamp(r.timestamp).strftime("%Y-%m-%d") == today]
        
        model_stats = {}
        task_stats = {}
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost_today = 0.0
        successful_requests = 0
        failed_requests = 0
        
        for record in today_records:
            if record.model_name not in model_stats:
                model_stats[record.model_name] = {
                    "count": 0,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0
                }
            model_stats[record.model_name]["count"] += 1
            model_stats[record.model_name]["total_cost_usd"] += record.cost_usd
            model_stats[record.model_name]["total_tokens"] += record.total_tokens
            
            if record.task_type not in task_stats:
                task_stats[record.task_type] = {
                    "count": 0,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0
                }
            task_stats[record.task_type]["count"] += 1
            task_stats[record.task_type]["total_cost_usd"] += record.cost_usd
            task_stats[record.task_type]["total_tokens"] += record.total_tokens
            
            total_prompt_tokens += record.prompt_tokens
            total_completion_tokens += record.completion_tokens
            total_cost_today += record.cost_usd
            
            if record.success:
                successful_requests += 1
            else:
                failed_requests += 1
        
        return {
            "total_cost_usd": round(self._total_cost_usd, 4),
            "total_tokens": self._total_tokens,
            "today": {
                "cost_usd": round(total_cost_today, 4),
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "requests": {
                    "total": len(today_records),
                    "successful": successful_requests,
                    "failed": failed_requests
                },
                "model_stats": model_stats,
                "task_stats": task_stats
            },
            "budget": self._budget.get_remaining(),
            "cache": {
                "size": len(self._result_cache),
                "ttl_seconds": self._cache_ttl
            }
        }
    
    def get_cost_forecast(self, requests_per_day: int = 100, avg_tokens_per_request: int = 1000) -> Dict[str, Any]:
        """获取成本预测"""
        avg_cost_usd = self._total_cost_usd / max(len(self._cost_records), 1)
        
        remaining_days_in_month = (datetime.now().replace(day=1) + timedelta(days=32)).day - datetime.now().day
        
        return {
            "daily_forecast_usd": round(avg_cost_usd * requests_per_day, 4),
            "monthly_forecast_usd": round(avg_cost_usd * requests_per_day * 30, 4),
            "remaining_month_forecast_usd": round(avg_cost_usd * requests_per_day * remaining_days_in_month, 4),
            "avg_cost_per_request_usd": round(avg_cost_usd, 6),
            "remaining_days_in_month": remaining_days_in_month
        }
    
    def get_model_list(self) -> List[Dict[str, Any]]:
        """获取模型列表"""
        return [
            {
                "name": model.name,
                "prompt_cost_usd_per_1k": model.prompt_cost_usd_per_1k,
                "completion_cost_usd_per_1k": model.completion_cost_usd_per_1k,
                "max_tokens": model.max_tokens,
                "capability": model.capability,
                "description": model.description
            }
            for model in self._models.values()
        ]
    
    def get_budget_alert(self) -> Dict[str, Any]:
        """获取预算告警"""
        budget = self._budget.get_remaining()
        daily_usage_ratio = budget["daily_used"] / max(budget["daily_limit"], 1)
        monthly_usage_ratio = budget["monthly_used"] / max(budget["monthly_limit"], 1)
        
        alerts = []
        level = "ok"
        
        if daily_usage_ratio > 0.9:
            alerts.append("每日 Token 预算即将耗尽")
            level = "warning"
        elif daily_usage_ratio > 0.7:
            alerts.append("每日 Token 预算使用超过 70%")
            level = "info"
        
        if monthly_usage_ratio > 0.9:
            alerts.append("每月 Token 预算即将耗尽")
            level = "warning" if level == "info" else "critical"
        elif monthly_usage_ratio > 0.7:
            alerts.append("每月 Token 预算使用超过 70%")
            if level == "ok":
                level = "info"
        
        return {
            "level": level,
            "alerts": alerts,
            "daily_usage_ratio": round(daily_usage_ratio * 100, 2),
            "monthly_usage_ratio": round(monthly_usage_ratio * 100, 2)
        }
    
    def clear_cache(self):
        """清除缓存"""
        self._result_cache.clear()


_cost_manager: Optional[CostManager] = None


def get_cost_manager() -> CostManager:
    """获取成本管理器"""
    global _cost_manager
    if _cost_manager is None:
        _cost_manager = CostManager()
    return _cost_manager


async def select_model_for_task(task_type: str, complexity: str = "medium") -> str:
    """选择适合任务的模型"""
    manager = get_cost_manager()
    return manager.select_model(task_type, complexity)


async def calculate_llm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """计算 LLM 调用成本"""
    manager = get_cost_manager()
    return manager.calculate_cost(model_name, prompt_tokens, completion_tokens)


async def check_token_budget(tokens_needed: int) -> bool:
    """检查 Token 预算"""
    manager = get_cost_manager()
    return manager.check_budget(tokens_needed)


async def record_llm_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    task_type: str,
    success: bool = True,
    error: str = None
):
    """记录 LLM 调用成本"""
    manager = get_cost_manager()
    manager.record_cost(model_name, prompt_tokens, completion_tokens, task_type, success, error)


async def get_cost_statistics() -> Dict[str, Any]:
    """获取成本统计信息"""
    manager = get_cost_manager()
    return manager.get_cost_stats()


async def get_cost_forecast_data(requests_per_day: int = 100, avg_tokens_per_request: int = 1000) -> Dict[str, Any]:
    """获取成本预测数据"""
    manager = get_cost_manager()
    return manager.get_cost_forecast(requests_per_day, avg_tokens_per_request)


async def get_model_list_data() -> List[Dict[str, Any]]:
    """获取模型列表数据"""
    manager = get_cost_manager()
    return manager.get_model_list()


async def get_budget_alert_data() -> Dict[str, Any]:
    """获取预算告警数据"""
    manager = get_cost_manager()
    return manager.get_budget_alert()


async def llm_with_cache(
    prompt: str,
    model_name: str,
    task_type: str,
    call_func: callable,
    *args,
    **kwargs
) -> str:
    """
    带缓存的 LLM 调用
    
    Args:
        prompt: 提示文本
        model_name: 模型名称
        task_type: 任务类型
        call_func: 实际调用函数
        *args: 额外位置参数
        **kwargs: 额外关键字参数
        
    Returns:
        LLM 生成结果
    """
    manager = get_cost_manager()
    cache_key = manager.generate_cache_key(prompt, model_name)
    
    cached = manager.get_cache(cache_key)
    if cached:
        app_logger.info(f"[CostManager] Cache hit for task_type: {task_type}, saved: ${cached['cost_usd']:.4f}")
        return cached["result"]
    
    result = await call_func(*args, **kwargs)
    
    cost_usd = manager.calculate_cost(model_name, 0, 0)
    manager.set_cache(cache_key, result, model_name, cost_usd)
    
    return result