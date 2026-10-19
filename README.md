# MeetingMind

面向会议资料的 RAG 与 Agent 应用。将会议文档或音频转成可检索的知识，支持带引用的问答、纪要与待办整理，以及需要人工确认的工具操作。

## 主要能力

- **会议知识问答**：说话人感知分块、关键词与向量混合召回、重排、引用及访问控制。
- **结构化整理**：通过 LangGraph 节点组织纪要、待办、约束与争议抽取，包含质量检查和结构修复。
- **受控工具执行**：参数 Schema、工具策略、人工确认、幂等和 PostgreSQL 审计；保留 Jira Cloud 接入。
- **异步处理**：RabbitMQ 投递确认、手动 ACK、延迟重试与死信队列。
- **可选音频输入**：独立 FunASR Worker 处理 WAV 转写，转写修订后进入检索链路。
- **实验扩展**：独立的待办抽取 LoRA/QLoRA 实验，不作为 Web 主链默认依赖。

## 处理流程

```text
会议文档 / WAV 音频
  → 解析 / 异步转写
  → 说话人感知分块与 PostgreSQL 正文存储
  → 关键词 + Dense 召回 → 加权融合 → Reranker
  → 带引用的回答 / 结构化会议结果
  → 工具参数校验 → 策略检查 → 人工确认 → 执行与审计
```

PostgreSQL 是正文和长期事实的权威源。检索可选 pgvector 或 Milvus；长期记忆的 Milvus 投影器尚未启用，不能将可选检索索引与记忆同步能力混为一谈。

## 技术栈

| 层 | 组件 |
| --- | --- |
| API 与数据契约 | FastAPI、Pydantic |
| Agent 编排 | LangGraph、Tool Calling、HITL |
| 检索 | PostgreSQL、BGE-M3、BGE Reranker；可选 pgvector / Milvus |
| 状态与任务 | PostgreSQL、Redis、RabbitMQ、aio-pika |
| 前端 | Vue 3、Vite、Element Plus、Pinia |
| 可选实验 | FunASR、Transformers、PEFT、bitsandbytes |

## 本地运行

当前开发方式为：宿主机 PostgreSQL，Docker Redis / RabbitMQ，后端与 Worker 在本机 Conda 环境运行，前端使用 Node/npm。

先准备 PostgreSQL，并根据模板填写本地配置。根目录 `.env` 用于 Compose，`backend/.env` 用于后端：

```bash
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up -d redis rabbitmq
```

在已有 Python Conda 环境中启动后端：

```bash
cd backend
pip install -r requirements-core.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动 Worker：

```bash
cd backend
python -m app.workers.run
```

前端：

```bash
cd frontend
npm install
npm run dev
```

健康检查：`GET http://127.0.0.1:8000/health`。可选 ASR 和微调环境分别使用 `requirements-asr.txt`、`requirements-finetuning.txt`；长期记忆的 `MEMORY_INDEX_WORKER_ENABLED` 保持关闭。

完整环境配置见 [API 与运行](docs/API与运行.md)。

## 演示与测试

本地服务就绪后可运行固定演示，覆盖 HTTP、权限拒绝、工具确认和队列恢复：

```bash
python scripts/demo_five_minute.py --base-url http://127.0.0.1:8000

# 后端契约测试
cd backend
pytest tests/contracts -q
```

前端测试与构建：

```bash
cd frontend
npm test -- --run
npm run build
```

演示说明见 [固定五分钟演示](docs/固定五分钟演示.md)。这些是运行入口，不表示本次文档更新重新执行了测试。

## 评测结果与适用范围

冻结评测包含 **28 场会议、100 条人工复核任务**，不能将其视为完整金标准或生产效果。已有记录如下：

| 项目 | 结果 | 测量范围 |
| --- | --- | --- |
| 混合检索 | Recall@5 = 0.0732 | 已知会议内排序、文本去重后统计，非全库检索 |
| 待办 / 约束规范化 | F1 = 0.713 / 0.467 | 候选规范化，非整场会议端到端抽取 |
| 云端结构化输出 | JSON 有效率 100% | 当前100条样本，只证明结构合法性 |
| 核心契约测试 | 120 passed | 已有契约记录，不代表生产容量验收 |

四种检索方案各10条的生成对比仅为抽样检查；25条合成提示注入样本的结果仅用于回归，不外推为生产安全率。详细设置与原始证据见 [真实会议评测收口](docs/真实会议评测收口.md) 和 [证据与限制](docs/证据与限制.md)。

## 当前边界

已完成本地工程演示，尚未完成真实 Jira 项目写入、全库检索效果、多节点容量或生产高可用验收。节点 Trace 为有界进程内记录；ASR 仍需多人会议标注集评测。

完整文档入口：[docs/README.md](docs/README.md)。

