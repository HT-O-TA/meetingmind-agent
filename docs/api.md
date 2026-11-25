# MeetingMind API 边界

业务接口前缀为 `/api/v1`。进程存活检查为`/live`，依赖就绪检查为`/ready`，`/health`仅作为`/ready`的兼容别名。除注册和登录外，主业务接口应携带：

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

## 认证与限流边界

- 除注册、登录和健康检查外，业务接口需要 Bearer JWT；后端会回查 PostgreSQL 用户状态，不只相信令牌中的历史信息。
- 当前 JWT 只有到期失效，没有退出当前设备、退出全部设备或刷新令牌能力。生产导向的有状态会话升级已经完成设计，但实施计划暂停，不能把它描述为现有能力。
- 注册按客户端 IP 限流；登录同时按客户端 IP 和用户名摘要限流。
- RAG、Agent普通/流式/批量查询、文档和音频任务创建、文档批量上传、失败任务人工重发以及任务长轮询按用户分别限流。管理员也不会绕过资源限流。
- 超出限制返回 `429`，并携带 `Retry-After`、`X-RateLimit-Limit`、`X-RateLimit-Remaining` 和 `X-RateLimit-Reset`。
- Redis 无法完成限流检查时，上述高风险或高成本入口返回 `503`；普通读取接口不受该限流门禁影响。

限流代码和离线契约测试已经存在，但截至 2026-11-24，当前本地 Redis 连接没有通过真实冒烟，因此不能声称限流已在真实部署环境验收。

Agent内部并行任务会在执行波次结束后检查累计失败率，默认达到30%时停止后续波次，并明确标记未执行任务。该机制限制单次运行中的失败扩散，但不等同于跨请求的状态型熔断器。

## 健康检查与请求关联

| 方法 | 路径 | 状态语义 |
|---|---|---|
| GET | `/live` | 只确认FastAPI进程可以响应，不访问PostgreSQL、Redis或RabbitMQ |
| GET | `/ready` | PostgreSQL或Redis失败返回503；RabbitMQ失败返回200并标记`degraded` |
| GET | `/health` | 兼容旧客户端，状态码和依赖检查与`/ready`一致 |

三项依赖并行检查，单项默认硬超时2秒。公开响应只返回依赖名称、`ok/error/degraded`状态和`latency_ms`，不返回异常原文、连接字符串或密钥。

后端为每次HTTP请求生成唯一的32位十六进制`X-Request-ID`，正常和异常响应会返回该响应头，浏览器也可通过CORS读取。客户端传入的合法ID只作为`correlation_id`。任务响应的`origin_request_id`保留最初创建任务时的服务端ID，重试和派生任务可沿用该ID。

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

Trace 不持久化，服务重启后清空，当前 Trace Token/成本字段没有真实采集值时仍保持 `0`。Agent 响应中的 `budget_ledger` 是独立的运行级预算快照：供应商返回 usage 时记录真实输入/输出 Token，否则明确保留最坏情况预留值；项目不把估算值伪装成真实成本。

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
- `citations` 列出检索证据，`answer_citations` 列出答案实际展示的引用。生成输出引用了未纳入本轮上下文的编号时，返回检索摘录，并在降级原因中标记 `invalid_answer_citations`。
- `retrieval_strategy`、`retrieval_sources`；
- `retrieval_latency_ms`、`generation_latency_ms`、`total_latency_ms`；
- `degradation` 与 `provenance`。

文档上传或重新解析后，如果正文已保存但索引未建成，文档状态为 `index_failed`。授权用户仍可读取文档，也可以通过文档任务入口重新处理。

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

普通、SSE 最终事件和批量响应都返回 `budget_ledger` 与 `context_manifest`。前者包含模型/节点计数方法、调用前估算、输出预留、供应商实际 usage、累计值与拒绝原因；后者包含上下文来源引用、哈希、优先级、原始/纳入长度、截断与丢弃原因。两者都不包含 Prompt 或证据正文。确认恢复沿用快照中的原 Agent Run 累计预算；预算快照缺失或损坏时拒绝恢复。

## API 暴露原则

生产环境只暴露上面列出的会议业务接口。评估使用离线命令，Embedding、向量存储和内部工作流不单独提供公网调试接口。
