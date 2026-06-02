"""Prompt模板市场API端点"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from app.agents.prompt_market import (
    get_prompt_market, TemplateCategory, TemplateType
)

router = APIRouter(tags=["Prompt模板"])


@router.get("/templates")
async def get_templates(category: Optional[str] = None):
    """获取所有模板"""
    market = get_prompt_market()
    
    if category:
        try:
            cat = TemplateCategory(category)
            templates = market.get_templates_by_category(cat)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的分类: {category}")
    else:
        templates = market.get_all_templates()
    
    return {"templates": templates}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """获取模板详情"""
    market = get_prompt_market()
    template = market.get_template(template_id)
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")
    
    import datetime
    return {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "category": template.category.value,
        "template_type": template.template_type.value,
        "content": template.content,
        "variables": template.variables,
        "examples": template.examples,
        "is_active": template.is_active,
        "version": template.version,
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
        "created_by": template.created_by
    }


@router.post("/templates")
async def create_template(
    name: str,
    description: str,
    category: str,
    content: str,
    variables: List[str],
    examples: Optional[List[str]] = None,
    created_by: Optional[str] = None
):
    """创建模板"""
    market = get_prompt_market()
    
    try:
        cat = TemplateCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的分类: {category}")
    
    template = market.create_template(
        name=name,
        description=description,
        category=cat,
        template_type=TemplateType.USER,
        content=content,
        variables=variables,
        examples=examples,
        created_by=created_by
    )
    
    return {"template_id": template.template_id, "message": "模板创建成功"}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    content: Optional[str] = None,
    variables: Optional[List[str]] = None,
    is_active: Optional[bool] = None
):
    """更新模板"""
    market = get_prompt_market()
    
    updates = {}
    if name:
        updates["name"] = name
    if description:
        updates["description"] = description
    if content:
        updates["content"] = content
    if variables:
        updates["variables"] = variables
    if is_active is not None:
        updates["is_active"] = is_active
    
    if not updates:
        raise HTTPException(status_code=400, detail="没有提供更新内容")
    
    success = market.update_template(template_id, **updates)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")
    
    return {"message": "模板更新成功"}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """删除模板"""
    market = get_prompt_market()
    success = market.delete_template(template_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")
    
    return {"message": "模板删除成功"}


@router.post("/templates/{template_id}/render")
async def render_template(template_id: str, **variables):
    """渲染模板"""
    market = get_prompt_market()
    result = market.render_template(template_id, **variables)
    
    if result is None:
        raise HTTPException(status_code=400, detail="模板渲染失败，可能缺少变量")
    
    return {"rendered_content": result}


@router.get("/templates/categories")
async def get_categories():
    """获取所有模板分类"""
    categories = [
        {"value": cat.value, "label": get_category_label(cat)}
        for cat in TemplateCategory
    ]
    return {"categories": categories}


@router.get("/domain-config")
async def get_domain_config():
    """获取领域配置"""
    market = get_prompt_market()
    config = market.get_domain_config()
    return {"config": config.get_all()}


@router.post("/domain-config")
async def update_domain_config(config: Dict[str, Any]):
    """更新领域配置"""
    market = get_prompt_market()
    domain_config = market.get_domain_config()
    
    for key, value in config.items():
        domain_config.set(key, value)
    
    return {"message": "领域配置更新成功"}


@router.post("/domain-config/reset")
async def reset_domain_config():
    """重置领域配置为默认值"""
    market = get_prompt_market()
    domain_config = market.get_domain_config()
    domain_config.reset_to_defaults()
    
    return {"message": "领域配置已重置为默认值"}


def get_category_label(category: TemplateCategory) -> str:
    """获取分类标签"""
    labels = {
        TemplateCategory.MEETING_SUMMARY: "会议总结",
        TemplateCategory.ACTION_ITEM: "待办事项",
        TemplateCategory.DECISION_RECORD: "决策记录",
        TemplateCategory.CONTROVERSY: "争议分析",
        TemplateCategory.QA_ANALYSIS: "问答分析",
        TemplateCategory.MEETING_PLAN: "会议规划",
        TemplateCategory.FOLLOW_UP: "跟进提醒",
        TemplateCategory.CUSTOM: "自定义"
    }
    return labels.get(category, category.value)
