"""FastAPI-Cache 使用示例

在 API 端点中使用 @cache 装饰器进行响应缓存
"""
from fastapi import APIRouter, Depends
from fastapi_cache.decorator import cache

router = APIRouter()


# ==================== 基本用法 ====================

@router.get("/meetings")
@cache(expire=60)  # 缓存 60 秒
async def list_meetings():
    """会议列表（带缓存）"""
    # 这个接口的响应会被缓存 60 秒
    # 相同的请求会直接返回缓存结果
    return {"meetings": []}


# ==================== 带参数的缓存 ====================

@router.get("/meetings/{meeting_id}")
@cache(expire=120)  # 缓存 120 秒
async def get_meeting(meeting_id: int):
    """会议详情（带缓存）"""
    # meeting_id 会自动作为缓存键的一部分
    return {"id": meeting_id, "title": "会议标题"}


# ==================== 自定义缓存键 ====================

from fastapi_cache import FastAPICache
from app.core.cache import cache_get, cache_set


async def custom_cache_key_builder(func, *args, **kwargs):
    """自定义缓存键构建器"""
    # 可以根据需要自定义缓存键
    return f"custom:{func.__name__}:{args}:{kwargs}"


@router.get("/search")
@cache(expire=300, key_builder=custom_cache_key_builder)
async def search_meetings(query: str, department: str = None):
    """搜索会议（自定义缓存键）"""
    return {"query": query, "results": []}


# ==================== 条件缓存 ====================

async def should_cache(response, *args, **kwargs):
    """根据响应内容决定是否缓存"""
    # 只缓存成功的响应
    if isinstance(response, dict) and response.get("success", True):
        return True
    return False


@router.post("/analyze")
@cache(expire=600, coder=None)  # POST 请求也可以缓存
async def analyze_meeting(meeting_id: int):
    """分析会议（条件缓存）"""
    return {"meeting_id": meeting_id, "analysis": {}}


# ==================== 清除缓存 ====================

from app.core.cache import cache_delete_pattern


@router.delete("/meetings/{meeting_id}/cache")
async def clear_meeting_cache(meeting_id: int):
    """清除会议缓存"""
    # 清除所有相关的缓存
    deleted = await cache_delete_pattern(f"api_cache:*meeting*{meeting_id}*")
    return {"deleted": deleted}


# ==================== 注意事项 ====================
"""
1. @cache 装饰器必须放在 @router 装饰器下面
2. 缓存键会自动包含路径参数和查询参数
3. POST/PUT/DELETE 请求也可以缓存，但需要谨慎使用
4. 数据更新后记得清除相关缓存
5. 缓存时间根据数据更新频率设置
"""
