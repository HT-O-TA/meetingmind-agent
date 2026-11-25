# API 与运行方式

## 启动后端

配置文件分工固定如下：

- 根目录 `.env`：供 Redis、RabbitMQ 等 Docker 基础设施使用；
- `backend/.env`：只供本机 Conda 后端使用。

在 `backend` 目录激活 `meetingmind-gpu`，安装 `requirements-core.txt` 后运行：

```bash
conda activate meetingmind-gpu
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康与就绪检查：

```text
GET /live    # 只确认后端进程仍能响应，不访问外部依赖
GET /ready   # 并行检查 PostgreSQL、Redis 和 RabbitMQ
GET /health  # 兼容旧调用，语义与 /ready 相同
```

`/ready`中，PostgreSQL和Redis是关键依赖，任一异常都会返回503；RabbitMQ异常时返回200，但整体状态标为`degraded`，表示同步读取仍可服务、异步任务暂不可用。每项检查默认最多等待2秒，可用`HEALTH_CHECK_TIMEOUT_SECONDS`调整。响应只包含依赖名称、状态和耗时，不暴露异常原文、连接地址或凭据。

每个HTTP请求都会由后端生成新的`X-Request-ID`并写回响应头。客户端传入的合法ID只作为关联标识。任务接口的`origin_request_id`记录首次创建任务时的服务端ID，可与RabbitMQ发布、消费、重试和死信日志关联。

后端启动时会初始化 PostgreSQL、Redis 相关缓存；异步任务还需要 RabbitMQ 和独立 Worker。

当前部署口径是：PostgreSQL 在宿主机，Redis、RabbitMQ 和 Milvus 使用 Docker；后端、Worker 和前端使用本机 Conda 环境。前端实际由 Conda 环境中的 Node/npm 运行。长期记忆索引 Worker 保持关闭，因为当前只有 PG outbox 和通用投影接口，尚未接入可执行的 Milvus 记忆投影器。

云模型默认名称为 `qwen3.7-flash`。冻结的 100 条评测历史结果使用 `qwen3.7-max-2026-06-08`，两者不能混写成同一次实验。

## 主要接口

| 前缀 | 用途 |
|---|---|
| `/api/v1/users` | 注册、登录、当前用户 |
| `/api/v1/meetings` | 会议和发言记录 |
| `/api/v1/documents` | 文档上传、解析、更新和删除 |
| `/api/v1/todos` | 待办 CRUD、批量创建和统计 |
| `/api/v1/rag/ask` | 检索、引用和回答 |
| `/api/v1/agents/query` | Agent 普通查询 |
| `/api/v1/agents/query-stream` | Agent SSE 流式事件 |
| `/api/v1/agents/batch` | Agent 批量请求 |
| `/api/v1/agents/confirmations/*` | 高风险操作确认和恢复 |
| `/api/v1/tasks` | 文档/音频任务创建、查询、取消、重试 |
| `/api/v1/feedback` | 反馈、Bad Case 和改进记录 |

除注册和登录外，业务接口通常需要：

```text
Authorization: Bearer <token>
```

## Redis 限流

当前关键入口默认启用 Redis 固定窗口限流：

| 入口 | 默认限制 |
|---|---:|
| 登录 | IP和用户名摘要各5次/5分钟 |
| 注册 | IP 3次/小时 |
| RAG问答 | 用户20次/分钟 |
| Agent普通查询 | 用户10次/分钟 |
| Agent流式查询 | 用户5次/分钟 |
| Agent批量查询 | 用户2次/分钟 |
| 文档/音频任务创建 | 用户10次/分钟 |
| 文档批量上传 | 用户2次/分钟 |
| 失败任务人工重发 | 用户5次/分钟 |
| 任务长轮询 | 用户5次/分钟 |

具体数值由两份 `.env.example` 中的 `RATE_LIMIT_*` 配置覆盖。超限返回429；Redis不可用时，受保护入口返回503。因此，本地启动后不能只看容器处于运行状态，还应确认 `/ready` 中的 Redis 状态，并对受保护接口执行一次真实请求。

当前限流已经通过离线契约测试，但本机 Redis 真实冒烟在 2026-11-24 仍因连接超时未完成。该事实不影响普通离线测试，但影响上线验收。

Agent内部并行执行还设置了失败率停止门禁：每个执行波次结束后计算累计失败率，默认达到30%就停止后续波次，并把尚未执行的任务标记为跳过。该阈值可通过`PARALLEL_FAILURE_THRESHOLD`调整。它用于限制失败扩散，不是会在多个请求之间保持Open/Half-Open状态的完整熔断器。

## 输入限制

- 文档：`txt/md/pdf/docx/csv/xlsx/xlsm`；
- 音频：当前只接受结构正确的 WAV；
- 服务端会同时检查扩展名、MIME、大小和文件实际结构；
- 空文件、伪装文件、图片、视频、旧版 `.doc` 等会在解析或入队前拒绝；
- 音频转写完成不代表识别准确，也不代表人工审核通过。

## 异步任务

文档处理和音频转写使用 RabbitMQ：API 创建任务后返回任务 ID，Worker 异步处理。任务支持状态查询、超时、重试、幂等、死信队列和失败重发。

Worker 单独启动：

```bash
cd backend
python -m app.workers.run
```

## 日志与排障

Compose中的Redis、RabbitMQ、Backend、Worker和Frontend统一使用Docker `local`日志驱动，默认单文件10 MiB、最多保留3个文件，可通过`DOCKER_LOG_MAX_SIZE`和`DOCKER_LOG_MAX_FILES`覆盖。修改这两个值后需要重新创建容器才能生效。

排障时先记录响应头中的`X-Request-ID`，再查后端访问日志和异常日志。接口返回任务 ID 时，用任务状态定位后台阶段，再查看 Worker 和队列状态。依赖故障可结合`/ready`中的状态和耗时判断。

本机告警脚本可从追加写入的访问日志和真实 RabbitMQ 采样中检测错误率、延迟、积压和新增死信，前台以 JSON 输出。常驻服务、集中式监控、外部通知和 Worker 心跳仍待接入。

## RAG 和 Agent 的区别

- RAG 接口适合“基于资料直接问一个问题”，返回回答、检索片段和引用。
- Agent 接口适合“需要判断任务类型、生成纪要/待办、规划步骤或调用工具”的问题。
- Agent 调用外部写工具时，不是模型说了算：还要经过工具策略、风险判断、必要的人工确认和审计。

## 开发测试

核心契约测试位于 `backend/tests/contracts/`；真实 Redis、PostgreSQL、RabbitMQ 集成测试位于 `backend/tests/integration/`。完整评估使用 `backend/scripts/evaluate.py`，合成数据报告必须明确标注为合成结果。
