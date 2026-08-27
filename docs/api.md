# MeetingMind API 边界

业务接口前缀为 `/api/v1`，健康检查为 `/health`。除注册和登录外，主业务接口应携带：

```http
Authorization: Bearer <token>
```

## 生产主链

| 前缀 | 端点 | 用途 |
|---|---|---|
| `/users` | `POST /register`、`POST /login`、`GET /me` | 最小身份认证；不提供后台用户管理 |
| `/meetings` | 列表、CRUD、状态、发言 CRUD/批量写入 | 会议事实数据 |
| `/documents` | 列表、上传、内容更新、元数据更新、删除、批量上传 | RAG 文档入口 |
| `/todos` | 列表、CRUD、批量创建、摘要 | 会议行动项 |
| `/rag` | `POST /ask` | ACL 前置的检索、引用、生成与降级 |
| `/agents` | `POST /query`、`/query-stream`、`/batch` | Agent 普通/SSE/批量入口 |
| `/agents/confirmations` | pending、history、查询、respond、resume | 高风险工具 HITL |
| `/feedback` | 反馈、Bad Case、分析、改进、验证、模式 | AI 反馈闭环 |
| `/tasks` | 文档/音频任务、查询、取消、清理、重发、等待 | RabbitMQ 任务生命周期 |

## 输入文件契约

- 文档入口只接受 `txt/md/pdf/docx/csv/xlsx/xlsm`，并联合校验扩展名、Content-Type、大小和实际内容结构；旧版 `.doc`、图片、视频、传感器文件及伪装文件不属于接口能力。
- 音频入口为 `POST /tasks/audio`，表单字段是 `meeting_id` 与 `file`，只接受可由标准库验证的 WAV MIME/RIFF 内容；支持 `Idempotency-Key`。
- 文档或 WAV 为空返回 422，超过限制返回 413，扩展名/MIME 不支持返回 415；失败文件不会进入解析或 RabbitMQ。
- 音频证据状态通过会议详情中的 `transcript_status` 返回：`pending/processing/completed/failed`。`transcript_revision` 表示当前证据版本，`transcript_metadata` 保存溯源、安全、复核和索引状态。
- `completed` 只表示转写工作结束，不等于准确率达标或人工审核通过；空转写或全部片段被安全隔离时不会生成可检索文档。
- 发言记录的 `security_status` 为 `passed/warning/quarantined`。授权用户仍可看到 quarantined 片段以便修订，但该片段不进入 Agent/RAG。

## 开发环境 Trace

`trace` Router 仅在 `APP_ENV=development` 或 `test` 注册：

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/trace/spans?limit=100` | 最近真实 Agent 节点 Span |
| GET | `/trace/spans/{span_id}` | 单个 Span |
| GET | `/trace/summary` | 有界进程存储的数量、成功率、平均耗时 |

Trace 不持久化，服务重启后清空；Token/成本没有真实采集值时保持 `0`，不生成模拟数据。

## RAG 请求示例

```http
POST /api/v1/rag/ask
Content-Type: application/json
Authorization: Bearer <token>

{
  "question": "上次评审会议决定了什么？",
  "meeting_id": 12,
  "top_k": 5,
  "use_llm": true
}
```

响应的 `data` 使用 `rag.v1` 契约，重点字段包括：

- `answer`、`chunks`、`citations`；
- `retrieval_strategy`、`retrieval_sources`；
- `retrieval_latency_ms`、`generation_latency_ms`、`total_latency_ms`；
- `degradation` 与 `provenance`。

## Agent 请求示例

```http
POST /api/v1/agents/query
Content-Type: application/json
Authorization: Bearer <token>

{
  "question": "根据会议结论创建 Jira 任务",
  "meeting_id": 12,
  "session_id": "sess_browser_tab",
  "enable_human_in_the_loop": true
}
```

若写工具需要确认，响应会包含 `requires_confirmation`、`confirmation_status` 和 `pending_action`。客户端通过 confirmation 接口批准或拒绝；批准后使用 `/confirmations/resume` 从后端保存的确认快照继续执行。

## 已移除接口

以下接口不再属于应用边界，也没有“打开开关即可恢复”的承诺：

- `/graph`、`/mcp`、`/multi-agent`、`/collaboration`；
- `/memory`、`/reflection`、`/dynamic-tools`；
- `/embedding`、`/vector-search` 底层调试接口；
- `/config`、`/templates`、`/tests`、`/workflow`；
- `/evaluation`、`/performance`、`/cost`。

评估改用离线命令，底层 Embedding/Vector 只由 RAG 主链内部调用。
