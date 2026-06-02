from fastapi import APIRouter
from app.core.response import Response
from app.services.text_process_service import TextProcessService
from app.schemas.text_process import (
    TextProcessRequest,
    TextExtractRequest,
)
from app.core.config import settings

router = APIRouter(tags=["文本处理"])


@router.post("/parse", summary="解析会议文本")
async def parse_meeting_text(request: TextProcessRequest):
    """
    解析会议文本，返回清洗后的文本、分句、切片、关键词和摘要
    
    - **content**: 会议文本内容
    - **chunk_size**: 切片大小（默认{settings.CHUNK_SIZE}）
    - **overlap**: 切片重叠大小（默认{settings.CHUNK_OVERLAP}）
    """
    service = TextProcessService()
    result = service.parse_meeting_text(request.content)
    
    # 应用自定义切片参数（如果传入了非默认值）
    if request.chunk_size != settings.CHUNK_SIZE or request.overlap != settings.CHUNK_OVERLAP:
        result['chunks'] = service.split_chunks(
            result['cleaned_text'], 
            chunk_size=request.chunk_size, 
            overlap=request.overlap
        )
    
    return Response(data=result)


@router.post("/extract-keywords", summary="提取关键词")
async def extract_keywords(request: TextExtractRequest):
    """
    从文本中提取关键词
    
    - **content**: 文本内容
    """
    service = TextProcessService()
    keywords = service.extract_keywords(request.content, top_n=15)
    result = [{"word": kw[0], "count": kw[1]} for kw in keywords]
    return Response(data=result)


@router.post("/generate-summary", summary="生成摘要")
async def generate_summary(request: TextExtractRequest):
    """
    生成文本摘要
    
    - **content**: 文本内容
    """
    service = TextProcessService()
    summary = service.generate_summary(request.content, max_length=500)
    return Response(data={"summary": summary})


@router.post("/extract-todos", summary="提取待办事项")
async def extract_todos(request: TextExtractRequest):
    """
    从会议文本中提取待办事项
    
    - **content**: 会议文本内容
    """
    service = TextProcessService()
    todos = service.extract_todo_items(request.content)
    return Response(data=todos)


@router.post("/split-sentences", summary="分句处理")
async def split_sentences(request: TextExtractRequest):
    """
    将文本按句子切分
    
    - **content**: 文本内容
    """
    service = TextProcessService()
    sentences = service.split_sentences(request.content)
    return Response(data={"sentences": sentences, "count": len(sentences)})


@router.post("/clean-text", summary="文本清洗")
async def clean_text(request: TextExtractRequest):
    """
    清洗文本（去除特殊字符、全角转半角等）
    
    - **content**: 原始文本内容
    """
    service = TextProcessService()
    cleaned = service.clean_text(request.content)
    return Response(data={"original_length": len(request.content), "cleaned_length": len(cleaned), "cleaned_text": cleaned})
