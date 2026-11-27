# MeetingMind

[![CI](https://github.com/HT-O-TA/meetingmind-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HT-O-TA/meetingmind-agent/actions/workflows/ci.yml?query=branch%3Amain)

面向会议资料的 RAG 与 Agent 应用。将会议文档或音频转成可检索的知识，支持带引用的问答、纪要与待办整理，以及需要人工确认的工具操作。

## 演示与验证

一分钟终端录屏覆盖 HTTP 上传、带引用回答、本地 Jira 确认门禁和 PostgreSQL 审计回归。 [观看录屏](docs/evidence/meetingmind-one-minute.mp4)

```mermaid
flowchart LR
  A[会议文档或音频] --> B[检索与访问控制]
  B --> C[带引用问答与结构化整理]
  C --> D[写操作人工确认]
  D --> E[工具执行与审计]
```

- [五分钟本地演示](docs/固定五分钟演示.md)覆盖权限拒绝、工具确认和队列恢复。按[运行指南](docs/API与运行.md)启动服务后，从仓库根目录执行：

```bash
python scripts/demo_five_minute.py --base-url http://127.0.0.1:8000
```

- [后端核心回归入口](backend/scripts/run_core_tests.sh)记录在后文「演示与测试」，README 记录 243 项通过。

| 核心结果 | 证据 |
|---|---|
| 100 条盲写路由测试，准确率 46% → 93%，路由 p95 83 ms | [规则基线](backend/evaluation/reports/route_eval_test_v4_rules.json) · [语义与分类头](backend/evaluation/reports/route_eval_test_v4_rules_semantic_head.json) |
| 同一批 40 条 QA，两位历史 Judge 按原提示词分别判 34/40、37/40 条回答的全部论断有依据 | [Opus 5.5](backend/evaluation/reports/faithfulness_qa40_judge_opus55.json) · [Sonnet 5](backend/evaluation/reports/faithfulness_qa40_judge_sonnet5.json) |

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

# 后端核心回归（243 项，无需外部服务）
cd backend
bash scripts/run_core_tests.sh -q
```

前端测试与构建：

```bash
cd frontend
npm test -- --run
npm run build
```

演示说明见 [固定五分钟演示](docs/固定五分钟演示.md)。这些是运行入口，不表示本次文档更新重新执行了测试。

## 评测结果（基线 → 当前）

冻结评测包含 **28 场会议、100 条人工复核任务**（单审核人复核，不是专家金标准）。每个数字都能追溯到 `backend/evaluation/reports/` 下的报告；留出集由独立 agent 盲写，跑之前冻结代码并记录哈希。

| 维度 | 数据集 | 基线 | 当前 | 报告 |
|---|---|---|---|---|
| 意图路由准确率 | 盲写一次性测试集 100 条（`route_eval_test_v4`） | 0.46（纯规则） | **0.93**（规则 + bge-m3 意图头），p95 83ms；剔除近重复后 0.93（N=84） | `route_eval_test_v4_rules_semantic_head.json` |
| 写操作人工确认召回 | 工具调用集，写操作 16 条（留出集 40 条） | 0.30（开发集，修复前） | **1.00**，未经确认的写入 0/40；同配置复跑仍为 16/16 | `tool_eval_heldout_v1_opus55.json` |
| 工具选择 / 参数准确率 | 同上，40 条 | — | 1.00 / 0.84 | 同上 |
| 约束 / 待办抽取 F1（非空 gold） | 冻结 100 条 / 28 场会议 | 0.158 / 0.139（qwen3.7-max） | **0.737 / 0.498**（Opus 5.5 + prompt v2，二者同时变更） | `meetingmind_real_v1_opus55_v2_100_scored.json`（含空 gold 的混合口径：0.467→0.833） |
| QA 引用 Precision | 同上 | 0.975 | 1.000 | 同上 |
| 历史 Judge 忠实度（答案级，全部论断都有片段依据） | 同上 40 条 QA，两个评判模型盲评 | 0.65 / 0.85（qwen3.7-max） | **34/40 与 37/40**（Opus 5.5，分别为两位评审的判定）；两评判一致判为不忠实的 1/40；注入无关句的探针 40/40 被识别 | `faithfulness_qa40_judge_{opus55,sonnet5}.json` |
| 会议内检索（已知 meeting_id，300 字块，k=5） | 40 条 QA | 发言级 Recall@5 0.073 / MRR 0.40 | 证据召回 0.293（上限 0.619）/ MRR 0.856 | `meetingmind_real_v1_chunk_retrieval.json` |
| 全库检索（不给 meeting_id，34 场会议 1626 块同池） | 40 条 QA 中 20 条针对具体议题的问题 | 会议内检索证据召回 0.461 | 找对会议 19/20（加重排 20/20），证据召回 0.333（加重排 0.379）；另 20 条"这场会议讲了什么"在全库下无法定位会议，单列 | `meetingmind_real_v1_corpus_retrieval.json` |

同一组 40 条历史 Opus QA 中，30 条可见片段缺少部分参考 ID，其中 17 条被单名审核者判为有无依据断言。参考 ID 齐全的 10 条中也有 3 条未通过。会议内 Top-5 的 29.32% 来自独立的分块排序实验。逐题对齐可定位证据缺口，根因仍需控制上下文后验证。 [逐题对照及连续分数汇总](backend/evaluation/reports/qa-evidence-and-score-diagnostics.json)

**忠实度盲审与复核**。对同一批 40 条历史 Opus 答案，单名人工判有依据 20/40。GPT-6.1 Sol 使用与人工共用的转写规则，与人工一致 33/40（逐题 Wilson 95% 区间 68.1%–91.3%）。该结果含规则同源效应。另从 10 场会议各取一条，两次独立会话在补充归属条款前后分别与人工一致 8/10 和 10/10，比较范围限于用于完善规则的同一子集。人工标签来自一位审核者。

**本地模型服务直连压测**（`scripts/bench_vllm_serving.py`，报告 `vllm_bench_qwen3_1p7b.json`）：vLLM 0.10 + Qwen3-1.7B fp16，单张 RTX 4060 8GB，负载为 40 条真实会议 QA（约 1.6k 字上下文，输出 ≤128 token），每档 64 请求，全部成功。

| 并发 | TTFT p50 / p95 (ms) | 端到端 p95 (ms) | 输出吞吐 (tok/s) |
|---|---|---|---|
| 1 | 93 / 169 | 1125 | 46 |
| 4 | 92 / 180 | 1310 | 156 |
| 8 | 105 / 211 | 1702 | 248 |
| 16 | 115 / 315 | 2354 | 347 |
| 32 | 609 / 906 | 3481 | 399 |

KV cache 只有 12,800 token（约 6 路 2k 请求），并发 16→32 时吞吐只多 15%，TTFT p95 却涨到约 3 倍，说明排队开始主导。所以本机适合把并发上限设在 16。1.7B 模型只能承担路由、改写这类轻任务，不能替换 Opus 规划。

**本机业务接口短测**。单 API、单 Worker、回环 HTTP、4 个账号。轻量检索、合成 Agent 普通与 SSE 入口、上传到向量任务完成共四组，每组并发 4 和 8，各档预热 8 次、计时 64 次。计时请求成功 512/512，HTTP 429、在途拒绝和意外失败均为 0/512。轻量检索关闭 Milvus、重排和生成，合成 Agent 固定等待 250ms。并发 8 时，轻量检索、合成 Agent 普通入口、SSE 完整响应、上传到向量子任务完成的成功 P95 分别为 519、318、384、524ms。

**轻量检索缓存复测**。本机 4 个账号，先等待测试文档完成向量索引，再依次发出 70 个不同请求、重放其中 30 个。100/100 请求成功，检索缓存命中 30/100，30 个重放全部命中。每次从缓存取到候选后仍由 PostgreSQL 校验 ACL 和软删除。该比例对应固定重放负载。

**本机多实例验收**。在独立 Compose 中运行 2 API + 2 Worker。跨实例同账号检索依次返回 200、200、429。两个 Worker 分别收到 1 个和 5 个任务，6/6 完成。两个 API 各允许 8 条合成 Agent SSE，第 9 条分别返回 503。两份 Prometheus 抓取记录了请求计数、延迟桶和在途量。Worker 强杀复测中，RabbitMQ 重投，另一 Worker 在领取锁到期后继续处理，32.41 秒内自动完成同一父任务，并复用原向量子任务。强杀 API 后旧流断开，重启后新流可完成，另一 API 保持就绪。供应商熔断使用模拟故障验证。

**代价与取舍**
- 换 Opus 后，抽取 p95 从 3.9s 升到 7.8s，token 用量约为原来的 23 倍。规划 p95 首轮测得 70.6s，同配置复跑为 17.7s（`tool_eval_heldout_v1_opus55_rerun2.json`，写确认仍为 16/16）。两轮各跑同一组 40 条工具规划任务，延迟差异的原因尚未隔离。
- 把规划换成 Sonnet 5 后（40 条，并发 4），p95 16s，与 Opus 复跑的 17.7s 基本持平，写操作确认召回却掉到 0.375（16 条写请求中 10 条没发起写操作：3 条建单给出空计划，7 条改单只调了查询），**所以没有采用**，见优化记录。
- 本地 1.7B 复杂度分类器的准确率不比规则高，p95 却有 1.35s，所以默认关闭。
- 长会话上下文组装（`scripts/run_memory_budget_control.py`，12 段由真实会议改写的会话）：v1 的条目上限按新近度丢掉早期关键事实，包装开销中位数约 202 Token，组装后反而比全量拼接多 12.6%。改为按和当前问题的词面重合竞争席位、并精简重复标签后，Token 中位数 726→584（比全量拼接少 9.5%），关键事实保留 34/41→36/41；剩下 5 条仍被条目上限卡掉（`memory_budget_longsession_v{1,2}.json`）。
- 受控检索策略优化（`scripts/optimize_retrieval.py`）在 40 条真实 QA 上按会议切分：开发集选出纯 Dense 权重（nDCG@5 0.643→0.675），验证集却降到 0.588、11 条中 7 条退化，**门禁拒绝**，在线仍用 0.3/0.7（`policy_optimization_real_v1.json`）。
- 引用 Precision 按参考证据 ID 计算。答案是否有足够依据见单独的忠实度盲审。

### 数据库与 OpenAPI

- PostgreSQL 通过 SQLAlchemy 模型管理用户、会议、文档、向量分块、待办、长期记忆和工具审计等表。空库启动时创建缺失表。已有库的结构变更按对应迁移脚本显式执行，例如工具审计表、用户权限字段和记忆时间戳。有旧数据时先确认目标版本与备份，再执行对应升级。 [表模型](backend/app/models) · [迁移脚本](backend/app/db/migrations)
- API 从 FastAPI 路由和请求、响应 Schema 自动生成 OpenAPI。后端启动后可打开 `/docs`（Swagger UI）、`/redoc` 和 `/openapi.json`。 [API 说明](docs/api.md)

### 工具变更记录 · Jira 创建工单

现有工具最初随企业工具接入进入仓库。后续安全改造补齐外部写入的参数校验、权限检查、人工确认、幂等和持久审计，影响工具注册与执行、确认恢复、审计表及已有库迁移。没有确认时策略返回 confirmation_required，经批准后才能进入执行。重复幂等键回放已留存结果。

本次复查对门禁与恢复跑了 13 项契约测试，全部通过。另在本机 PostgreSQL 跑了持久审计与幂等回归，1 项通过。历史 main CI #54 通过，覆盖契约测试和 PostgreSQL 审计集成。确认演示是本机策略验证，真实 Jira 写入须在隔离租户单独验证。 [工具首次接入](https://github.com/HT-O-TA/meetingmind-agent/commit/bf28cd7) · [安全改造](https://github.com/HT-O-TA/meetingmind-agent/commit/f2b14cd) · [CI #54](https://github.com/HT-O-TA/meetingmind-agent/actions/runs/45592341536)

## 当前边界

已完成本地工程演示，尚未完成真实 Jira 项目写入、多节点容量或生产高可用验收；全库检索为离线复现同一融合策略，未走服务 API。节点 Trace 为有界进程内记录；ASR 仍需多人会议标注集评测。

查看 [文档索引](docs/README.md)、[MeetingMind 项目解析](docs/meetingmind项目解析.md) 或 [本机验收报告](backend/evaluation/reports/local-acceptance)。

