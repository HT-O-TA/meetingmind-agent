"""配置管理API端点"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.core.config_center import get_config_center, ConfigCategory, ConfigSource
from app.core.logger import app_logger

router = APIRouter(tags=["配置管理"])


@router.get("/config/all")
async def get_all_configs():
    """获取所有配置"""
    config_center = get_config_center()
    return {"configs": config_center.get_full_configs()}


@router.get("/config")
async def get_config_by_key(key: str):
    """根据key获取配置"""
    config_center = get_config_center()
    item = config_center.get_config_item(key)
    
    if not item:
        raise HTTPException(status_code=404, detail=f"配置项不存在: {key}")
    
    return item


@router.get("/config/category/{category}")
async def get_configs_by_category(category: str):
    """按分类获取配置"""
    try:
        cat = ConfigCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的分类: {category}")
    
    config_center = get_config_center()
    configs = config_center.get_by_category(cat)
    
    return {"category": category, "configs": configs}


@router.get("/config/summary")
async def get_config_summary():
    """获取配置摘要（脱敏）"""
    config_center = get_config_center()
    return config_center.get_all()


@router.post("/config/{key}")
async def update_config(key: str, value: Any):
    """更新配置值"""
    config_center = get_config_center()
    
    success = config_center.set(key, value, source=ConfigSource.DATABASE)
    
    if not success:
        raise HTTPException(status_code=400, detail=f"配置更新失败: {key}")
    
    app_logger.info(f"[API] 配置已更新: {key}")
    return {"message": "配置更新成功", "key": key, "value": value}


@router.post("/config/batch")
async def update_config_batch(configs: Dict[str, Any]):
    """批量更新配置"""
    config_center = get_config_center()
    success_count = 0
    failed_keys = []
    
    for key, value in configs.items():
        if config_center.set(key, value, source=ConfigSource.DATABASE):
            success_count += 1
        else:
            failed_keys.append(key)
    
    app_logger.info(f"[API] 批量配置更新完成: {success_count}成功, {len(failed_keys)}失败")
    
    return {
        "message": "批量更新完成",
        "success_count": success_count,
        "failed_keys": failed_keys
    }


@router.post("/config/reload")
async def reload_config():
    """重新加载配置"""
    config_center = get_config_center()
    config_center.reload()
    
    app_logger.info("[API] 配置已重新加载")
    return {"message": "配置已重新加载"}


@router.get("/config/categories")
async def get_categories():
    """获取所有配置分类"""
    return {"categories": [cat.value for cat in ConfigCategory]}
