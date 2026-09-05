# MeetingMind

MeetingMind 是一个面向真实会议资料的 RAG + Agent 应用。仓库只保留能形成证据链的检索、结构化抽取、安全工具调用、异步任务、ASR、微调实验与可复现部署，不再维护“概念齐全但没有业务闭环”的框架。

### 当前冻结证据

| 项目 | 当前结果 | 解释 |
|---|---:|---|
| 冻结评测集 | 100 条 / 28 场会议 | `gold=false`，100 条均由 `reviewer=ht` 人工审核 |
| QA 检索 | Hybrid Recall@5 = 0.0732 | 已知会议内排序，不是全库检索；文本去重后统计 |
| 候选规范化 | 待办 F1 = 0.713；约束 F1 = 0.467 | 不是从整场会议原文重新抽取的端到端 F1 |
| 云端结构化输出 | JSON 有效率 100% | 100 条，37,171 tokens；只证明结构化链路可运行 |
| 核心契约测试 | 120 passed | 仅覆盖代码契约，不等同于生产容量验收 |

生成对比目前只是 smoke：四种检索方案各跑 10 条，共 40 次请求，不作为正式问答效果或简历优劣结论。固定五分钟演示已在本地 PostgreSQL、Redis、RabbitMQ、API 和 Worker 上跑通，脱敏汇总见 `backend/evaluation/reports/meetingmind_five_minute_demo_closeout.json`。

## 唯一正式主链

```text
会议文档 / WAV 音频
→ 文档解析，或 RabbitMQ + FunASR 转写
→ 说话人感知分块
→ PostgreSQL 权威正文/VectorChunk + Dense 索引（pgvector/轻量模式；可选 Milvus 需同步）
→ PostgreSQL 关键词召回 + Dense 召回
→ 0.3 / 0.7 加权融合 + BGE Reranker
→ RAG 回答与引用
→ LangGraph 确定性业务节点或 Tool Agent
→ 参数 Schema → ToolPolicy → HITL → ToolExecutor → PostgreSQL 审计
```

## 保留能力与真实性边界

| 能力 | 当前实现 | 仍需补齐 |
|---|---|---|
| RAG | PostgreSQL 权威块、BM25 风格关键词召回、PG Dense/可选 Milvus、加权融合、Reranker、引用、ACL、降级字段 | 真实评测已完成一轮；全库检索、Milvus 增量同步和生产容量仍未验收 |
| Agent | 静态 LangGraph；路由、检索、纪要/待办/争议、计划执行、风险确认、质量门禁、结构修复 | 真实业务数据上的路由与端到端效果 |
| 工具调用 | 会议/文档工具；Jira Cloud REST v3；Schema、策略、HITL、幂等和审计 | Jira 站点凭据与真实项目写入演示 |
| 异步任务 | RabbitMQ confirm、manual ACK、延迟重试、DLQ、幂等任务状态 | 多节点高可用与真实容量验收 |
| ASR | 严格 WAV 准入；独立 FunASR Worker；原始/安全证据分区、逐段注入隔离、版本化修订、状态机和 RAG 证据入库 | 脱敏多人会议真值和 CER/DER |
| LoRA/QLoRA | Qwen3-0.6B 待办抽取教学实验和统一评测 | 真实会议标注集；当前合成结果不可外推 |
| 评估 | 冻结 28 场会议/100 条任务，完成候选规范化、检索基线、云端结构化输出和抽样端到端对比 | 会议内检索尚非全库检索；生成对比为每种方案 10 条抽样，不能宣称 Reranker 整体领先 |
| Trace | 有界进程内节点 Trace，只记录真实节点、耗时、重试、输出和错误 | 跨进程持久化不在当前范围 |
| 部署 | 前后端镜像、PostgreSQL、Redis、RabbitMQ、Worker Compose 和 CI | TLS、备份、Secret Manager、HA、生产容量 |

## 已删除的非主线内容

深度瘦身阶段已直接删除，而不是保留关闭开关：

- Knowledge Graph / Neo4j 与图谱前端；
- MCP Client/Server、飞书/GitHub/Notion 示例和动态工具发现；
- Multi-Agent、Agent 通信、Prompt 市场、通用 ReAct/CoT 分支；
- HyDE、Multi-Query、Step-back、Sparse/RRF 策略 B/M；
- 图片/视频“多模态骨架”，仅保留已经跑通的本地 ASR；
- PostgreSQL/Redis/向量三套长期记忆与反思记忆，改为有界会话窗口；
- RAGAS、DSPy、重复评估/回归服务；
- 动态配置中心、后台用户管理、成本/性能/模板/测试等管理接口；
- Prometheus/Grafana、通用 Fault Tolerance、Locust 等非 AI 主链展示内容。

如要恢复任何能力，先提出可验证的业务问题、数据集和验收指标，再重新实现；不从 Git 历史直接恢复成默认功能。

## 技术栈

| 层 | 选型 |
|---|---|
| API / Schema | FastAPI、Pydantic、JSON Schema |
| Agent | LangGraph、自定义状态、Tool Calling、HITL |
| 检索 | PostgreSQL tsvector/VectorChunk/pgvector、可选 Milvus Dense、BGE-M3、BGE-Reranker |
| 数据与状态 | PostgreSQL、Redis |
| 异步任务 | RabbitMQ、aio-pika、Worker |
| ASR | FunASR（独立可选环境） |
| 微调 | Transformers、PEFT、bitsandbytes（独立实验环境） |
| 前端 | Vue 3、Vite、Element Plus、Pinia |

## API 边界

生产环境注册：

- `/api/v1/users`：注册、登录、当前用户；
- `/api/v1/meetings`、`/documents`、`/todos`：会议知识业务；
- `/api/v1/rag`：带 ACL 与引用的 RAG；
- `/api/v1/agents`：查询、SSE、批量和 HITL；
- `/api/v1/feedback`：反馈与 Bad Case；
- `/api/v1/tasks`：异步任务状态。

`/api/v1/trace` 只在 development/test 注册。完整字段见 [API 文档](docs/api.md)。

## 本地开发

后端核心环境：

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-core.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

本地模型、ASR 和微调分别使用 `requirements-asr.txt`、`requirements-finetuning.txt` 及对应阶段文档，不安装进 Web/Worker 镜像。

## Compose 启动

默认 Compose 只启动 PostgreSQL、Redis、RabbitMQ、后端、Worker 和前端：

```bash
cp .env.example .env
python3 scripts/preflight_deploy.py --mode development
docker-compose up -d --build
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8080/
```

默认镜像不包含 Torch、FunASR、本地 Embedding/Reranker 模型或 Milvus，因此 Compose 通过表示 Web 主链可启动，不表示完整模型能力或生产环境已经验收。

## 测试与评估

零外部依赖的主链契约：

```bash
cd backend
python3 -m unittest \
  tests.contracts.test_stage0_boundaries \
  tests.contracts.test_rag_mainline_contract -v
```

完整核心测试：

```bash
cd backend
./scripts/run_core_tests.sh -q
```

Compose 启动后，先运行当前固定五分钟演示（HTTP 正常/权限拒绝、工具确认、队列恢复）：

```bash
python scripts/demo_five_minute.py --base-url http://127.0.0.1:8000
```

旧的四项 Demo 入口仍保留在 `scripts/run_fixed_demos.py`，用于追溯公开 WAV ASR 和 LoRA 抽取验证，不代表当前五分钟演示的必需依赖。

前端：

```bash
cd frontend
npm test -- --run
npm run build
```

统一离线评估：

```bash
cd backend
python3 scripts/evaluate.py --allow-synthetic \
  --dataset evaluation/datasets/sample_eval.jsonl \
  --output evaluation/reports/sample_report.json
```

冻结 Prompt Injection 合成回归：

```bash
cd backend
python3 scripts/evaluate.py --allow-synthetic \
  --dataset evaluation/datasets/prompt_injection_synthetic_v1.jsonl \
  --thresholds evaluation/prompt_injection_synthetic_thresholds.json \
  --enforce-thresholds \
  --output evaluation/reports/prompt_injection_synthetic_v1.json
```

仓库样例标记为 `synthetic`，只能验证公式、规则和控制流回归。Prompt Injection 报告中的零误报/零漏报只对当前 25 条合成样本成立；简历和 README 中的生产效果数字必须来自冻结的真实或公开人工标注数据。

## 学习路线与证据

文档总入口：先看 [docs/README.md](docs/README.md)，再按其中的阅读顺序进入大白话主文档。以下阶段文档保留用于追溯历史决策和验证证据。

- [项目总览（大白话）](docs/项目总览_大白话.md)
- [输入预处理层技术说明](docs/架构解析/输入预处理层.md)
- [记忆层技术说明](docs/架构解析/记忆层.md)
- [证据与限制（大白话）](docs/证据与限制_大白话.md)

- [阶段 1：RAG 权限、路由与统一评估](docs/优化路径记录/05_阶段1_RAG权限路由与统一评估.md)
- [阶段 2：Agent 安全工具闭环](docs/优化路径记录/06_阶段2_Agent安全工具闭环.md)
- [阶段 3：RabbitMQ 失败恢复](docs/优化路径记录/07_阶段3_RabbitMQ失败恢复与容量基线.md)
- [阶段 4：真实 ASR](docs/优化路径记录/08_阶段4_真实ASR与音频证据闭环.md)
- [阶段 5：LoRA/QLoRA](docs/优化路径记录/09_阶段5_LoRA与QLoRA可复现实验.md)
- [阶段 6：部署与 CI](docs/优化路径记录/10_阶段6_部署CI固定Demo与求职证据.md)
- [阶段 7：深度瘦身与 AI 应用岗位聚焦](docs/优化路径记录/11_阶段7_深度瘦身与AI应用岗位聚焦.md)

项目的学习目标不是记住框架名称，而是能回答：为什么保留这条主链、输入输出契约是什么、失败边界在哪里、指标如何复现、哪些结论目前还不能说。
