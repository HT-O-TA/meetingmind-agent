# MeetingMind API 文档

本文档按当前代码实现整理。所有业务接口统一挂载在 `/api/v1` 下，健康检查接口为 `/health`。

---

## 通用说明

### 认证

部分接口依赖登录态，通过请求头传递 JWT：

```http
Authorization: Bearer <token>
```

当前主要受保护接口包括用户信息、会议、文档、待办等业务接口。Agent、RAG、向量化、评估、配置等接口当前未统一强制鉴权，实际权限应以后端依赖注入为准。

### 统一响应

多数 CRUD 接口使用 `Response`：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

分页接口使用 `PageResponse`：

```json
{
  "code": 200,
  "message": "success",
  "data": [],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

Agent、配置、模板、协作类接口中有部分直接返回业务 JSON，不包裹 `Response`。

---

## 用户接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/users/register` | 用户注册 |
| `POST` | `/api/v1/users/login` | 用户登录，返回访问令牌 |
| `GET` | `/api/v1/users/me` | 获取当前用户信息 |
| `PUT` | `/api/v1/users/me` | 更新当前用户信息 |
| `GET` | `/api/v1/users` | 用户列表 |

---

## 会议接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/meetings` | 会议列表，支持分页 |
| `POST` | `/api/v1/meetings` | 创建会议 |
| `GET` | `/api/v1/meetings/{meeting_id}` | 获取会议详情 |
| `PUT` | `/api/v1/meetings/{meeting_id}` | 更新会议 |
| `PATCH` | `/api/v1/meetings/{meeting_id}/status` | 更新会议状态 |
| `DELETE` | `/api/v1/meetings/{meeting_id}` | 删除会议 |
| `GET` | `/api/v1/meetings/{meeting_id}/speeches` | 获取会议发言记录 |
| `POST` | `/api/v1/meetings/{meeting_id}/speeches` | 新增发言记录 |
| `POST` | `/api/v1/meetings/{meeting_id}/speeches/bulk` | 批量新增发言记录 |
| `PUT` | `/api/v1/meetings/{meeting_id}/speeches/{speech_id}` | 更新发言记录 |
| `DELETE` | `/api/v1/meetings/{meeting_id}/speeches/{speech_id}` | 删除发言记录 |

创建会议请求体示例：

```json
{
  "title": "项目周会",
  "description": "同步项目进度",
  "organizer_name": "张三",
  "department": "研发部",
  "meeting_type": "weekly",
  "participants": "[\"张三\", \"李四\"]",
  "raw_transcript": "会议原文..."
}
```

---

## 文档接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/documents` | 文档列表，支持分页 |
| `POST` | `/api/v1/documents/upload` | 上传单个文档 |
| `POST` | `/api/v1/documents/batch-upload` | 批量上传文档 |
| `GET` | `/api/v1/documents/{doc_id}` | 获取文档详情 |
| `PUT` | `/api/v1/documents/{doc_id}` | 更新文档元数据 |
| `PUT` | `/api/v1/documents/{doc_id}/content` | 更新文档内容 |
| `DELETE` | `/api/v1/documents/{doc_id}` | 删除文档 |

上传接口使用 `multipart/form-data`。支持格式由配置项 `ALLOWED_FILE_EXTENSIONS` 控制，默认包括 `txt`、`pdf`、`docx`、`doc`、`md`。

---

## 待办接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/todos` | 待办列表，支持分页和筛选 |
| `POST` | `/api/v1/todos` | 创建待办 |
| `POST` | `/api/v1/todos/bulk` | 批量创建待办 |
| `GET` | `/api/v1/todos/summary/stats` | 待办统计 |
| `GET` | `/api/v1/todos/{todo_id}` | 获取待办详情 |
| `PUT` | `/api/v1/todos/{todo_id}` | 更新待办 |
| `DELETE` | `/api/v1/todos/{todo_id}` | 删除待办 |

创建待办请求体示例：

```json
{
  "meeting_id": 1,
  "title": "完成项目报告",
  "description": "整理本周项目进展",
  "assignee_name": "李四",
  "priority": "high",
  "due_date": "2026-06-10T18:00:00"
}
```

---

## 文本处理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/text-process/parse` | 清洗、分句、切片、关键词和摘要 |
| `POST` | `/api/v1/text-process/extract-keywords` | 提取关键词 |
| `POST` | `/api/v1/text-process/generate-summary` | 生成摘要 |
| `POST` | `/api/v1/text-process/extract-todos` | 提取待办 |
| `POST` | `/api/v1/text-process/split-sentences` | 分句 |
| `POST` | `/api/v1/text-process/clean-text` | 文本清洗 |

---

## 向量化接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/embedding/encode` | 单文本向量化 |
| `POST` | `/api/v1/embedding/batch-encode` | 批量向量化 |
| `POST` | `/api/v1/embedding/similarity` | 计算两段文本相似度 |
| `GET` | `/api/v1/embedding/status` | 向量化服务状态 |

单文本向量化请求：

```json
{
  "content": "需要向量化的文本"
}
```

---

## 向量检索接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/vector-search/search` | 按文本检索向量块 |
| `GET` | `/api/v1/vector-search/chunks/{document_id}` | 获取指定文档的所有向量块 |
| `GET` | `/api/v1/vector-search/status` | 检索服务状态 |

检索请求：

```json
{
  "content": "项目风险有哪些？",
  "top_k": 5,
  "meeting_id": 1,
  "department": "研发部",
  "similarity_threshold": 0.7
}
```

服务会根据运行环境返回 `pgvector` 或 `lightweight` 模式。

---

## RAG 问答接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/rag/ask` | 基于知识库检索并可选调用 LLM 生成回答 |

请求示例：

```json
{
  "question": "这个会议有哪些待办？",
  "top_k": 5,
  "meeting_id": 1,
  "department": "研发部",
  "similarity_threshold": 0.7,
  "use_llm": true
}
```

---

## RAG 评估接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/evaluation/dataset` | 获取内置评估数据集 |
| `POST` | `/api/v1/evaluation/evaluate` | 评估单个自定义问题 |
| `POST` | `/api/v1/evaluation/evaluate/{question_id}` | 按内置问题 ID 评估 |
| `POST` | `/api/v1/evaluation/evaluate-all` | 评估整个内置数据集 |

内置数据集当前为 233 个正例和 30 个负例。`evaluate-all` 的 `top_k` 和 `skip_llm` 不传时分别读取 `EVAL_TOP_K`、`EVAL_SKIP_LLM`。

---

## Agent 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/agents/query` | Agent 普通查询 |
| `POST` | `/api/v1/agents/query-stream` | Agent SSE 流式查询 |
| `POST` | `/api/v1/agents/batch` | 批量查询 |
| `POST` | `/api/v1/agents/memory` | 记忆操作 |
| `GET` | `/api/v1/agents/memory/stats` | 记忆统计 |
| `GET` | `/api/v1/agents/architecture` | Agent 架构信息 |
| `GET` | `/api/v1/agents/prompts` | Prompt 模板列表 |
| `GET` | `/api/v1/agents/tools` | 工具列表 |
| `GET` | `/api/v1/agents/errors/recent` | 最近错误 |
| `GET` | `/api/v1/agents/monitor/status` | 监控状态 |
| `GET` | `/api/v1/agents/confirmations/pending` | 待确认请求 |
| `GET` | `/api/v1/agents/confirmations/history` | 确认历史 |
| `GET` | `/api/v1/agents/confirmations/{request_id}` | 确认请求详情 |
| `POST` | `/api/v1/agents/confirmations/respond` | 响应确认请求 |

查询请求：

```json
{
  "question": "总结这个会议，并列出待办和争议点",
  "meeting_id": 1,
  "document_ids": [1, 2],
  "session_id": "session-001",
  "enable_memory": true,
  "enable_tool_calling": false,
  "enable_human_in_the_loop": false
}
```

流式响应为 SSE：

```text
data: {"type":"start","data":{"question":"...","phase":"初始化"}}

data: {"type":"thought","data":{"step":1,"agent_id":"plan_agent","phase":"plan","thought":"..."}}

data: {"type":"final","data":{"success":true,"task_type":"qa","answer":"..."}}

data: [DONE]
```

---

## Agent 协作接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/agent-messages` | 获取 Agent 消息 |
| `POST` | `/api/v1/agent-messages/broadcast` | 广播消息 |
| `POST` | `/api/v1/agent-messages/send` | 发送点对点消息 |
| `POST` | `/api/v1/agent-messages/clear` | 清空消息 |
| `POST` | `/api/v1/agents/register` | 注册协作 Agent |
| `POST` | `/api/v1/agents/unregister` | 注销协作 Agent |
| `GET` | `/api/v1/agents/list` | 协作 Agent 列表 |
| `POST` | `/api/v1/tasks/create` | 创建协作任务 |
| `POST` | `/api/v1/tasks/{task_id}/dispatch` | 分发任务 |
| `POST` | `/api/v1/tasks/{task_id}/update` | 更新任务 |
| `GET` | `/api/v1/tasks` | 任务列表 |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情 |
| `GET` | `/api/v1/tasks/pending` | 待处理任务 |
| `GET` | `/api/v1/tasks/agent/{agent_id}` | 指定 Agent 的任务 |

---

## 配置接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/config/all` | 获取完整配置 |
| `GET` | `/api/v1/config?key=...` | 按 key 获取配置 |
| `GET` | `/api/v1/config/category/{category}` | 按分类获取配置 |
| `GET` | `/api/v1/config/summary` | 获取脱敏摘要 |
| `POST` | `/api/v1/config/{key}` | 更新单项配置 |
| `POST` | `/api/v1/config/batch` | 批量更新配置 |
| `POST` | `/api/v1/config/reload` | 重新加载配置 |
| `GET` | `/api/v1/config/categories` | 配置分类列表 |

---

## Prompt 模板接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/templates` | 模板列表 |
| `GET` | `/api/v1/templates/{template_id}` | 模板详情 |
| `POST` | `/api/v1/templates` | 创建模板 |
| `PUT` | `/api/v1/templates/{template_id}` | 更新模板 |
| `DELETE` | `/api/v1/templates/{template_id}` | 删除模板 |
| `POST` | `/api/v1/templates/{template_id}/render` | 渲染模板 |
| `GET` | `/api/v1/templates/categories` | 模板分类 |
| `GET` | `/api/v1/domain-config` | 获取领域配置 |
| `POST` | `/api/v1/domain-config` | 更新领域配置 |
| `POST` | `/api/v1/domain-config/reset` | 重置领域配置 |

---

## 测试辅助接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/tests/run-unit-tests` | 运行单元测试 |
| `GET` | `/api/v1/tests/run-tool-tests` | 运行工具测试 |
| `GET` | `/api/v1/tests/run-agent-tests` | 运行 Agent 测试 |

---

## 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 应用和 Redis 连接状态 |

