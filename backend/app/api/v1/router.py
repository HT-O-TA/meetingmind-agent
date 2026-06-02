from fastapi import APIRouter
from app.api.v1.endpoints import users, meetings, documents, todos, text_process, embedding, vector_search, rag, evaluation, agents, tests, config, collaboration, templates

api_router = APIRouter()

api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["会议"])
api_router.include_router(documents.router, prefix="/documents", tags=["文档"])
api_router.include_router(todos.router, prefix="/todos", tags=["待办"])
api_router.include_router(text_process.router, prefix="/text-process", tags=["文本处理"])
api_router.include_router(embedding.router, prefix="/embedding", tags=["向量化服务"])
api_router.include_router(vector_search.router, prefix="/vector-search", tags=["向量检索"])
api_router.include_router(rag.router, prefix="/rag", tags=["RAG 问答"])
api_router.include_router(evaluation.router, prefix="/evaluation", tags=["RAG 评估"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agent 智能助手"])
api_router.include_router(tests.router, prefix="/tests", tags=["测试"])
api_router.include_router(config.router, prefix="", tags=["配置管理"])
api_router.include_router(collaboration.router, prefix="", tags=["Agent协作"])
api_router.include_router(templates.router, prefix="", tags=["Prompt模板"])
