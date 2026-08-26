# MeetingMind

MeetingMind 是一个正在收敛中的企业会议智能应用学习项目。项目目标不是堆叠 AI 概念，而是形成一条可运行、可评估、可部署、可用于技术讲解的会议知识处理闭环。

当前仓库的正式主线是：

```text
会议文本/文档或 WAV 音频
→ 文本解析，或 RabbitMQ + FunASR 转写与匿名说话人时间线
→ 说话人感知分块
→ PostgreSQL 正文存储与 Milvus Dense 索引
→ PostgreSQL 关键词召回 + Dense 召回
→ 加权融合 + BGE Reranker
→ Simple RAG 或 LangGraph Tool Agent
→ 参数 Schema / ToolPolicy / HITL / ToolExecutor / PostgreSQL 审计
```

## 当前真实性状态

| 能力 | 状态 | 说明 |
|---|---|---|
| 文档解析与分块 | 已实现，待完整集成基线 | 正式策略为说话人感知混合分块 |
| RAG HTTP 主链路 | 已建立版本化契约 | `/api/v1/rag/ask` 使用方案 A，强制认证并返回引用/降级/时延 |
| 关键词召回 | 已实现 | PostgreSQL `tsvector + ts_rank_cd`，属于 BM25 风格检索 |
| Dense 召回 | 已实现，依赖运行环境 | Milvus 优先，失败回退 pgvector 或轻量余弦检索 |
| Fusion + Reranker | 已实现契约测试 | 0.3 关键词权重 + 0.7 Dense 权重，权重仍需离线评测 |
| Agent | 已收敛默认边界 | 默认只保留 Simple RAG、确定性业务节点和 Tool Agent；检索继承用户 ACL |
| ToolPolicy / HITL | 安全链路与持久审计已验证 | Jira Cloud 为唯一正式目标；缺少本机凭据，真实站点联调待完成 |
| RabbitMQ 任务 | 可靠性基线已完成 | Confirm、manual ACK、延迟重试、DLQ、幂等、用户隔离及单机轻量容量已验证 |
| RAG 评估 | 离线命令已统一 | 支持 RAG/抽取/工具/路由/系统指标；当前没有可对外引用的真实效果数字 |
| KG / Neo4j | 可选增强，默认关闭 | 不进入正式 RAG 请求路径 |
| MCP | 可选框架，默认关闭 | 尚未完成唯一真实外部 Server 联调 |
| ASR | 真实本地闭环，可选启用 | WAV → RabbitMQ → FunASR → 会议正文/时间戳/匿名说话人；公开烟测已完成，会议领域基线待真实数据 |
| 图片/视频多模态 | 骨架，默认关闭 | 不计入已实现能力 |
| LoRA / QLoRA | 尚未完成 | 训练目录、数据和对比实验仍待建设 |

文档 ACL、软删除回查和答案引用已完成代码/契约及 PostgreSQL 集成验证。当前仍不能将 Sparse/RRF、完整多模态、真实企业系统写入、端到端生产部署或合成样例/历史性能数字宣传为已完成能力。

## 正式 RAG 路径

```text
POST /api/v1/rag/ask
→ RAGService
→ Dense 召回
   → Redis 精确缓存
   → Milvus 召回 chunk_id
   → PostgreSQL 回查完整正文
   → 失败时 pgvector / Python 余弦回退
→ PostgreSQL 关键词召回
→ 按 chunk_id 去重和加权融合
→ 可选 KG 候选扩展（默认关闭）
→ Reranker 从候选池精排到最终 top_k
→ LLM 生成或返回检索内容
```

正式策略明确不包含 Sparse、RRF、Query Rewrite、HyDE、Multi-Query 或 Step-back。这些历史实现只有在离线评测证明收益后才允许重新进入主线。

详细代码走读见：

- [RAG 主链路走读与契约基线](docs/优化路径记录/03_RAG主链路走读与契约基线.md)
- [主链路真实性审计](docs/优化路径记录/02_主链路真实性审计.md)
- [Agent 主链路与阶段 0 运行基线](docs/优化路径记录/04_Agent主链路与阶段0基线.md)
- [阶段 1 RAG 权限、路由与统一评估](docs/优化路径记录/05_阶段1_RAG权限路由与统一评估.md)
- [阶段 2 Agent 安全工具闭环](docs/优化路径记录/06_阶段2_Agent安全工具闭环.md)
- [阶段 3 RabbitMQ 失败恢复与容量基线](docs/优化路径记录/07_阶段3_RabbitMQ失败恢复与容量基线.md)
- [阶段 4 真实 ASR 与音频证据闭环](docs/优化路径记录/08_阶段4_真实ASR与音频证据闭环.md)

## 正式 Agent 边界

默认 LangGraph 包含两类业务路径：

1. Simple RAG：安全检查、风险判断、检索、确定性问答/纪要/待办/争议节点、质量校验。
2. Tool Agent：规划、工具风险检查、必要时 HITL、执行、重规划和质量校验。

ReAct、CoT 和深度 LLM 反思代码暂时保留，但默认不注册到正式图中。Query Rewrite、反思记忆和 Multi-Agent 同样默认关闭或退出默认 Router。

## API 暴露边界

生产环境默认只注册：

- 用户、会议、文档、待办；
- 文本处理；
- RAG 与 Agent；
- 用户反馈；
- 异步任务状态。

Embedding、底层向量检索、评估、运行配置、Prompt 模板、Trace、性能、记忆、动态工具、反思和成本接口只在 `development` 或 `test` 环境注册。

以下历史 Router 不再进入默认应用：

- HTTP 测试执行器；
- Workflow mock；
- Agent Collaboration；
- Multi-Agent。

KG 和 MCP Router 只有在对应配置显式开启时才注册。

## 技术栈

| 层次 | 当前选型 |
|---|---|
| API | FastAPI、Pydantic、Uvicorn |
| 数据访问 | SQLAlchemy 2.0 Async、PostgreSQL |
| 关键词检索 | PostgreSQL tsvector / ts_rank_cd |
| Dense 检索 | Milvus，pgvector/轻量模式降级 |
| Embedding / Reranker | BGE-M3、BGE-Reranker（运行时依赖模型） |
| Agent | LangGraph、自定义状态与工具体系 |
| 缓存与状态 | Redis |
| 异步任务 | RabbitMQ、aio-pika、Worker |
| 可选图谱 | Neo4j |
| 前端 | Vue 3、Vite、Element Plus、Pinia |
| 观测 | Trace、Prometheus 指标框架 |

## 配置原则

复制示例配置后再填入本机信息：

```bash
cp backend/.env.example backend/.env
```

以下能力默认关闭：

```dotenv
RETRIEVAL_STRATEGY=A
ENABLE_SPARSE_RETRIEVAL=false
ENABLE_QUERY_REWRITE=false
ENABLE_HYDE=false
ENABLE_MULTI_QUERY=false
ENABLE_STEP_BACK=false
ENABLE_KNOWLEDGE_GRAPH=false
ENABLE_NEO4J_PERSISTENCE=false
ENABLE_MULTIMODAL=false
ENABLE_ASR=false
ENABLE_MCP_SERVER=false
ENABLE_AGENT_WORKER=false
```

`.env` 是本机私有文件，不应提交 API Key、Token 或密码。可公开配置应同步到 `.env.example`，真实密钥只通过环境变量或后续的 SecretProvider 注入。

## 测试

### 零外部依赖契约测试

当前最小基线不要求 FastAPI、数据库、Milvus、Redis 或模型：

```bash
cd backend
python3 -m unittest discover -s tests/contracts -v
```

该基线验证：

- RAG 层与检索层的方法和字段契约；
- Milvus 成功路径的缓存写入；
- BM25/Dense 融合后的完整正文；
- 精排候选池与最终 `top_k`；
- Agent 图只编译一次；
- 正式 Agent 默认节点边界；
- 生产、内部、可选和退役 Router 的暴露策略；
- 未经验证的可选能力默认关闭。

### 完整测试

当前轻量核心测试不要求数据库、Redis、Milvus 或本地模型。首次创建环境：

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-core.txt
./scripts/run_core_tests.sh -q
```

2026-08-26 完成阶段 4 代码收敛后的轻量核心基线为 `171 passed, 2 skipped`；另有 Jira 客户端单元测试 `8 passed`。真实 PostgreSQL ACL、工具审计/幂等、Redis 任务状态和 RabbitMQ 重试/DLQ 集成测试共 `4 passed`，并另行完成一次真实 FunASR 队列业务烟测。两个核心跳过项依赖未安装的模型能力；Milvus、会议领域真值、真实 Jira 站点与真实文档/模型容量仍需单独验收，不能把当前通过数解释为完整生产验收。

统一离线评估命令：

```bash
cd backend
python3 scripts/evaluate.py --allow-synthetic \
  --dataset evaluation/datasets/sample_eval.jsonl \
  --output evaluation/reports/sample_report.json
```

仓库样例明确标记为 `synthetic`，只验证公式和报告格式。真实回归必须换成冻结的 `sample_kind=real` 数据，并显式启用回归阈值。

## 开发启动

Python 依赖：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

阶段 0 已使用全新 Compose PostgreSQL/Redis 数据卷验证后端冷启动和 `/health`。完整一键部署、模型服务拆分、Milvus 编排及前端联动仍在收敛中，因此暂不能把整套 Compose 视为生产部署验收完成。

## 项目路线

后续工作严格按照[JD 对标与项目收敛路线](docs/JD对标与项目收敛路线.md)推进：

1. 完成真实性审计、主链路和测试环境收敛；
2. 建立 RAG 离线评估、引用、ACL 和指标；
3. 完成 ToolPolicy、HITL、审计和一个真实企业写工具；
4. 完成 RabbitMQ 失败恢复和容量基线；
5. 接入一种真实 ASR；
6. 建立会议抽取 LoRA/QLoRA 对比实验；
7. 完成可复现部署、Demo、报告和简历证据。

所有对外描述和简历数字都必须能绑定到代码、测试命令、数据版本和实验报告。

## 当前未满足的完成标准

- 已有无 mock 的 WAV → RabbitMQ → FunASR → PostgreSQL 证据链路；尚无从会议输入到真实 Jira 写入的完整外部业务闭环；
- 已有统一评估命令，但尚无冻结真实数据生成的正式指标；
- 文档 ACL 和答案引用已完成，Milvus/真实数据规模下的效果与容量仍待验证；
- Jira 已替换为真实 REST v3 客户端并完成合同测试，但因缺少站点凭据与项目权限，尚未完成真实外部写演示；
- RabbitMQ 单机失败恢复与轻量容量基线已完成；多节点 quorum 高可用和真实文档/模型容量尚未验证；
- 真实 FunASR 与公开样例/队列烟测已完成，但缺少脱敏多人会议真值，尚无会议领域 CER/DER；
- LoRA/QLoRA 对比实验尚未完成；
- Docker 一键部署尚未完成验证。

这些限制会随路线执行逐项关闭，并在每个里程碑中留下代码、测试和学习记录。
