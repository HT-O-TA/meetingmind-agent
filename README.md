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
| QA 答案忠实度（论断级，全部论断有片段依据的比例） | 同上 40 条 QA，两个评判模型盲评 | 0.65 / 0.85（qwen3.7-max） | **0.85 / 0.925**（Opus 5.5）；两评判一致判为不忠实的 1/40；注入无关句的探针 40/40 被识别 | `faithfulness_qa40_judge_{opus55,sonnet5}.json` |
| 会议内检索（已知 meeting_id，300 字块，k=5） | 40 条 QA | 发言级 Recall@5 0.073 / MRR 0.40 | 证据召回 0.293（上限 0.619）/ MRR 0.856 | `meetingmind_real_v1_chunk_retrieval.json` |
| 全库检索（不给 meeting_id，34 场会议 1626 块同池） | 40 条 QA 中 20 条针对具体议题的问题 | 会议内检索证据召回 0.461 | 找对会议 19/20（加重排 20/20），证据召回 0.333（加重排 0.379）；另 20 条"这场会议讲了什么"在全库下无法定位会议，单列 | `meetingmind_real_v1_corpus_retrieval.json` |
| 回归测试 | pytest 核心套件 | 120 | 243 passed | `scripts/run_core_tests.sh` |

**本地部署压测**（`scripts/bench_vllm_serving.py`，报告 `vllm_bench_qwen3_1p7b.json`）：vLLM 0.10 + Qwen3-1.7B fp16，单张 RTX 4060 8GB，负载为 40 条真实会议 QA（约 1.6k 字上下文，输出 ≤128 token），每档 64 请求，全部成功。

| 并发 | TTFT p50 / p95 (ms) | 端到端 p95 (ms) | 输出吞吐 (tok/s) |
|---|---|---|---|
| 1 | 93 / 169 | 1125 | 46 |
| 8 | 105 / 211 | 1702 | 248 |
| 16 | 115 / 315 | 2354 | 347 |
| 32 | 609 / 906 | 3481 | 399 |

KV cache 只有 12,800 token（约 6 路 2k 请求），并发 16→32 时吞吐只多 15%，TTFT p95 却涨到约 3 倍，说明排队开始主导。所以本机适合把并发上限设在 16。1.7B 模型只能承担路由、改写这类轻任务，不能替换 Opus 规划。

**代价与取舍**
- 换 Opus 后，抽取 p95 从 3.9s 升到 7.8s，token 用量约为原来的 23 倍。规划 p95 首轮测得 70.6s，同配置复跑为 17.7s（`tool_eval_heldout_v1_opus55_rerun2.json`，写确认仍为 16/16），首轮长尾更像中转偶发慢，按 18s 左右看待。
- 把规划换成 Sonnet 5 后（40 条，并发 4），p95 16s，与 Opus 复跑的 17.7s 基本持平，写操作确认召回却掉到 0.375（16 条写请求中 10 条没发起写操作：3 条建单给出空计划，7 条改单只调了查询），**所以没有采用**，见优化记录。
- 本地 1.7B 复杂度分类器的准确率不比规则高，p95 却有 1.35s，所以默认关闭。
- 受控检索策略优化（`scripts/optimize_retrieval.py`）在 40 条真实 QA 上按会议切分：开发集选出纯 Dense 权重（nDCG@5 0.643→0.675），验证集却降到 0.588、11 条中 7 条退化，**门禁拒绝**，在线仍用 0.3/0.7（`policy_optimization_real_v1.json`）。
- 引用不是由 LLM-as-judge 判定，而是与人工 gold 的证据 ID 做匹配。

## 当前边界

已完成本地工程演示，尚未完成真实 Jira 项目写入、多节点容量或生产高可用验收；全库检索为离线复现同一融合策略，未走服务 API。节点 Trace 为有界进程内记录；ASR 仍需多人会议标注集评测。

完整文档入口：[docs/README.md](docs/README.md)。

