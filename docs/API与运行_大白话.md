# API 与运行方式（大白话）

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

健康检查：

```text
GET /health
```

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

## RAG 和 Agent 的区别

- RAG 接口适合“基于资料直接问一个问题”，返回回答、检索片段和引用。
- Agent 接口适合“需要判断任务类型、生成纪要/待办、规划步骤或调用工具”的问题。
- Agent 调用外部写工具时，不是模型说了算：还要经过工具策略、风险判断、必要的人工确认和审计。

## 开发测试

核心契约测试位于 `backend/tests/contracts/`；真实 Redis、PostgreSQL、RabbitMQ 集成测试位于 `backend/tests/integration/`。完整评估使用 `backend/scripts/evaluate.py`，合成数据报告必须明确标注为合成结果。
