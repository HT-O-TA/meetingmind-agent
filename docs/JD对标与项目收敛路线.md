# MeetingMind：大模型应用开发岗位对标与项目收敛路线

## 1. 项目目标

MeetingMind 不再追求覆盖尽可能多的 AI 概念，而是收敛为一个可运行、可评估、可部署、可用于面试讲解的企业会议智能应用。

核心业务闭环：

```text
会议文档/音频
→ 解析、转写与结构化抽取
→ 分块和知识库入库
→ BM25 + Dense Retrieval + Reranker
→ LangGraph Agent 问答与任务处理
→ ToolPolicy / HITL
→ 一个真实企业系统写入
→ 评估、追踪和反馈
```

项目最终需要证明四件事：

1. 能构建可靠的 LLM/RAG/Agent 应用，而不只是调用模型 API。
2. 能用数据和指标解释技术选型及优化结果。
3. 能处理异步任务、外部系统、安全和故障等工程问题。
4. 具备数据构建与 LoRA/QLoRA 微调的基本实践能力。

本项目的统一实现原则是：所有路由、抽取和工具执行都必须有结构化 Schema、置信度/失败边界和可追踪结果；任何外部写操作都必须经过 ToolPolicy、必要时 HITL，并保留审计记录。

## 2. JD 能力矩阵

| JD 能力 | 当前项目证据 | 当前判断 | 目标产出 | 优先级 |
|---|---|---|---|---|
| Python / FastAPI / Async | FastAPI、SQLAlchemy Async、异步服务 | 已具备，需收敛接口 | 一条稳定 API 主链路及集成测试 | P0 |
| LLM API 接入 | `LLMService`、OpenAI-compatible API | 已具备 | 超时、重试、结构化输出、调用指标 | P0 |
| Prompt Engineering | Prompt 模板、任务 Prompt、反思 Prompt | 分散且缺版本化 | Prompt 注册、版本、评测集关联 | P1 |
| 模型路由 | `ModelRouter`，turbo/plus/max | 有规则路由，无供应商容灾 | 保留任务×复杂度路由，记录路由、降级和成本 | P1 |
| RAG | PG BM25、Milvus Dense、Reranker | 核心能力较强 | 唯一正式检索链路和离线指标 | P0 |
| 分块 | 说话人感知语义分块及数据集 | 有实验基础 | 固化策略、基线和回归测试 | P0 |
| RAG 评估 | Recall/MRR、RAGAS、回归框架 | 多套评估并存 | 一套离线评估命令和报告 | P0 |
| Agent / LangGraph | 路由、计划、执行、反思 | 分支过多 | 保留 Simple RAG 与 Tool Agent 两条路径 | P0 |
| Function Calling / Tool Use | ToolManager、ToolExecutor、元数据 | 已具备 | 真实只读工具和真实写工具闭环 | P0 |
| MCP | Client、Server、Discovery、Manager | 框架较完整，入口分散 | 接入一个真实 MCP Server 并统一审计 | P1 |
| 安全与 HITL | ToolPolicy、风险分级、人工确认 | 已有框架 | 低/中/高风险集成测试与审计记录 | P0 |
| 异步任务 | RabbitMQ、Worker、任务状态 | 文档链路已有，多媒体未接入 | 耗时任务排队、重试、幂等、状态查询 | P1 |
| 结构化输出 | 任务 Prompt、状态和证据字段 | 缺少统一 Schema 治理 | Pydantic/JSON Schema、非法输出修复和版本追踪 | P0 |
| 多模态 | FunASR WAV 正式入口；旧图片/视频骨架默认关闭 | 真实公开样例和队列闭环已验证，缺会议真值 | 冻结脱敏多人会议集，补 CER/DER | P1 |
| 微调 | 当前没有完整训练闭环 | 缺失 | 会议待办抽取 LoRA/QLoRA 对比实验 | P1 |
| 数据工程 | 会议分块数据、RAG 评测数据 | 有基础，标注规范不足 | 数据卡、切分、质量检查、版本管理 | P1 |
| 部署 | Docker Compose、服务依赖 | 有基础，GPU 部署不明确 | CPU 基础部署 + 可选模型服务说明 | P1 |
| 可观测性 | Trace、Prometheus、性能指标 | 功能较多但需验证 | 请求级 trace、延迟、Token、工具结果 | P1 |
| 测试 | Unit/Integration/Load/RAG 测试 | 覆盖面较广，真实性不一 | 主链路测试矩阵与可重复命令 | P0 |
| 权限与数据安全 | 权限过滤、注入防护、软删除框架 | 部分实现 | 文档 ACL 检索过滤及删除一致性测试 | P2 |
| KG-RAG | 条件触发、Neo4j、实体链接框架 | 加分项，不是主线 | 保留可选增强，限制投入 | P2 |

## 3. 模块去留决策

### 3.1 保留并重点完善

以下能力直接对应常见 JD，也是项目的核心面试证据：

- `llm_service.py`：统一模型调用入口。
- `model_router.py`：保留轻量任务与复杂度路由。
- `semantic_chunker.py`：保留说话人感知分块。
- `bm25_retriever.py`、`vector_store_milvus.py`、`reranker.py`：组成唯一 RAG 主链路。
- `rag_service.py`：作为 RAG 编排入口。
- 统一路由指令：`task_type`、`complexity`、`model_tier`、`confidence`、`sub_tasks`。
- Pydantic/JSON Schema：约束纪要、决策、待办和工具参数输出。
- LangGraph 的状态、路由、计划与工具执行主链路。
- ToolManager、ToolExecutor、ToolPolicy、HITL。
- RabbitMQ、任务状态和 Worker 框架。
- RAG 离线评估、回归测试、Trace 和性能指标。
- PostgreSQL、Milvus、Redis：分别承担事实存储、向量检索、缓存/状态职责。

### 3.2 收缩为可选框架

以下能力有面试价值，但不能继续挤占主线时间：

- Neo4j/KG：仅作为条件性检索增强，不作为默认必经路径。
- 反思系统：保留确定性检查和统一质量门禁，复杂反思记忆降为可选。
- MCP：保留双向协议能力，先只验证一个真实外部 MCP Server。
- 多模型路由：保留模型档位路由，不立即实现复杂跨供应商容灾。
- 多模态视频：保留接口和数据结构，不在第一阶段实现完整音画融合。
- 多租户、索引版本切换、在线无停机重建：只保留设计说明。

### 3.3 删除或停用候选

执行删除前必须先做引用分析和回归测试。本阶段只确定候选范围：

- Milvus Sparse 及旧三路 RRF 描述和残留配置。
- 未接入主链路的 HyDE、Step-back、MultiQuery 等多套 Query Rewrite 分支。
- `dspy_rag.py` 等未形成真实实验结果的可选 RAG 路线。
- 重复的旧多模态 API 路线与新本地感知骨架，最终只保留一个入口。
- 飞书、Jira、Notion、Email 多个 mock 客户端：只保留一个真实写入目标，其余改为 MCP 示例或移除。
- Multi-Agent 通信、复杂协作等没有核心业务闭环支撑的分支。
- 重复的 memory service：最终保留清晰的会话状态和业务长期记忆两层。
- 重复 API：评估、测试、性能、反思等开发接口按用途合并或仅在开发环境注册。

## 4. 必须补充的能力

### 4.1 真实业务闭环

第一条正式闭环建议选择：

```text
会议文本或音频
→ 纪要/决策/待办抽取
→ RAG 追问并返回引用
→ 用户确认
→ 创建真实 Jira Issue 或飞书任务
→ 保存外部任务 ID 和执行审计
```

验收标准：无 mock 返回，失败可见，操作可追踪，高风险写入需要确认。

### 4.2 统一结构化输出

为纪要、待办、工具参数和反思结果定义 Pydantic Schema，至少验证：

- JSON 合法率；
- 必填字段完整率；
- 非法输出重试或修复；
- Prompt 版本和模型版本可追踪。

输出证据统一保留 `source_id`、`source_type`、`speaker`、`timestamp`、`uncertainties` 和 `degradation_info`，优先用于文本会议链路，不要求现在恢复完整视频感知。

### 4.3 置信度与降级

- 任务类型不确定：进入保守 fallback，不执行外部写工具。
- 复杂度不确定：降低执行复杂度或模型档位，但不改变已确定的业务任务。
- 阈值由路由评测集确定，并写入 Trace；不直接把旧版本的 `0.65` 当成事实。

### 4.4 统一评估体系

保留一套主评估命令，输出：

- Retrieval：Recall@K、MRR、nDCG；
- Generation：Faithfulness、Answer Relevancy、引用准确率；
- Extraction：Precision、Recall、F1、JSON 合法率；
- Tool：选择准确率、参数准确率、成功率、HITL 触发准确率；
- System：平均/P95 延迟、吞吐、错误率、Token 和成本。

所有简历数字必须能由脚本重新生成。

### 4.5 微调实验

微调作为独立学习增强模块，不进入第一阶段线上主链路。

任务选择：会议待办与决策的结构化抽取。

```text
原始会议片段
→ 人工标注 instruction/input/output
→ 数据质量检查
→ Train/Validation/Test 划分
→ 小模型 LoRA/QLoRA
→ Prompt-only / Few-shot / Fine-tuned 三组对比
```

推荐验收指标：

- 字段级 Precision、Recall、F1；
- 负责人和截止时间准确率；
- JSON Schema 合法率；
- 幻觉字段比例；
- 推理延迟和显存占用。

训练框架可以在模型确定后选择 Transformers + PEFT，或 LLaMA-Factory。项目只保留训练配置、数据处理、评估和推理适配，不自研训练框架。

### 4.6 生产工程最小集

- RabbitMQ：重试、死信、prefetch 和幂等键。
- 外部 API：超时、重试、熔断和错误分类。
- 安全：SecretProvider 接口，默认环境变量实现。
- 审计：记录用户、工具、风险、确认结果、外部结果 ID。
- 权限：至少完成文档级 ACL 到 RAG 召回过滤。
- 部署：开发 Compose 可复现，模型服务与 Web 服务解耦。
- 检索存活校验：Milvus/KG 返回的 chunk 必须回 PostgreSQL 校验软删除、权限和正文一致性。
- 失败边界：工具次数、修复次数、单步超时、连续失败和外部写操作重放均有上限。

## 5. 分阶段学习与实施路线

### 阶段 0：真实性审计与收敛

目标：让文档、配置和代码描述一致。

- 标记已实现、mock、骨架和停用能力。
- 修正 README 中 Sparse/RRF 等旧描述。
- 确定唯一 RAG 和 Agent 主链路。
- 建立核心测试清单。

产出：真实架构图、模块去留表、可复现启动说明。

### 阶段 1：RAG 核心能力

目标：能够完整解释并量化知识库问答。

- 固化分块、BM25、Dense、Fusion、Rerank。
- 统一路由指令和结构化输出 Schema，记录模型档位、置信度和降级动作。
- 建立离线评估集和回归阈值。
- 实现引用溯源与权限过滤。
- 记录延迟和检索阶段指标。

产出：RAG 对比报告和可运行 Demo。

### 阶段 2：Agent 与真实工具闭环

目标：证明 Agent 能安全地产生业务动作。

- 收敛 LangGraph 路由。
- 接通一个真实企业写工具。
- 完成 ToolPolicy、HITL 和审计。
- 统一入口为“参数 Schema 校验 → ToolPolicy → HITL → ToolExecutor → 审计”。
- 测试错误参数、拒绝确认、外部失败和幂等重试。

产出：会议待办到外部任务系统的完整演示。

### 阶段 3：异步任务与稳定性

目标：证明系统能处理耗时任务和失败恢复。

- 文档/音频任务进入 RabbitMQ。
- 增加并发限制、超时、重试、死信和任务状态。
- 做基础负载测试并记录 P95。

产出：任务生命周期图和容量测试报告。

### 阶段 4：真实 ASR 或多模态

目标：增加一个真实、可量化的多模态能力。

- 优先只接入 FunASR 或一个可靠 ASR 服务。
- 保留说话人和时间戳元数据。
- 视频视觉理解延后。

产出：音频到会议证据、纪要和待办的闭环。

执行状态（2026-08-26）：已完成 FunASR WAV 正式入口、RabbitMQ Worker、句级时间戳/匿名说话人、持久证据和公开样例真实烟测。纪要与待办当前是明确标注需人工核验的规则初稿/候选；正式会议领域 CER/DER 受脱敏真值数据阻塞。详见 `docs/优化路径记录/08_阶段4_真实ASR与音频证据闭环.md`。

### 阶段 5：LoRA/QLoRA 微调

目标：证明具备数据构建、训练和评估能力。

- 建立脱敏会议抽取数据集。
- 完成小模型 LoRA/QLoRA。
- 与 Prompt-only 和 Few-shot 做公平对比。
- 分析收益、成本和适用边界。

产出：训练配置、数据卡、实验报告、推理 Demo。

执行状态（2026-08-26）：已完成 76 条项目自编合成待办数据、meeting_id 隔离切分、Qwen3-0.6B LoRA/QLoRA 真实单卡训练、Prompt-only/3-shot/LoRA/QLoRA 同协议评测和推理烟测。LoRA 在 16 条合成测试集上的业务字段 F1 为 0.919，QLoRA 为 0.824；这些数字只证明模板化教学闭环，不能外推到真实会议。官方 AliMeeting4MUG AID 完整真值仍受 ModelScope Token 与数据使用确认阻塞。详见 `docs/优化路径记录/09_阶段5_LoRA与QLoRA可复现实验.md`。

### 阶段 6：部署、文档与简历

目标：将技术工作转换成可核验的求职成果。

- 整理一键部署和环境依赖。
- 录制三个固定 Demo。
- README 只保留真实能力和可复现指标。
- 将简历描述绑定到代码、测试和报告。

## 6. 第一轮执行清单

下一轮代码工作按以下顺序进行：

1. 审计路由与服务引用，确定唯一正式主链路。
2. 修正 README 和配置中的过期能力描述。
3. 关闭未使用的 Query Rewrite、Sparse 和重复多模态入口。
4. 明确核心测试集合，并运行当前基线。
5. 选择 Jira 或飞书作为唯一真实企业写入目标。
6. 建立微调目录规范和数据 Schema，但暂不开始训练。

## 7. 完成标准

项目达到岗位对标要求时，应能提供以下证据：

- 一条无 mock 的端到端业务链路；
- 一套可重复运行的 RAG/抽取/工具评估；
- 一组真实延迟、准确率、成功率和成本指标；
- 一次高风险外部写操作的 HITL 和审计记录；
- 一套 RabbitMQ 失败恢复与幂等测试；
- 一份 LoRA/QLoRA 微调前后对比报告；
- 一份准确区分已实现、可选和规划能力的 README。

## 8. 旧版本内容映射

`docs/解析.md` 中的优化内容已经按岗位价值融入前 1-7 节。本节只保留来源映射，避免把旧版本重新变成独立开发主线。

### 已吸收

以下内容虽然在旧版本设计中完整，但与当前收敛目标相比恢复成本过高：

- Qwen3-VL 视频抽帧、音画时间线融合；
- FunASR + CAM++ 全套说话人分离，阶段 4 再单独接入 ASR；
- HyDE、问题分解、同义词扩展同时启用；
- 通用 ReAct 五轮循环和复杂 Plan DAG；
- 多个企业平台的专用 mock 客户端；
- 完整跨供应商模型容灾；
- 在线无停机索引重建和复杂索引版本管理。

### 当前执行顺序

```text
1. 统一路由指令
2. 结构化输出 Schema
3. 检索后 PG 权限/存活校验
4. ToolPolicy + HITL + 审计闭环
5. 路由、抽取和工具评测集
6. RabbitMQ 失败边界
7. 真实 ASR
8. LoRA/QLoRA 对比实验
```

这组补充能恢复旧版本中最有岗位价值的设计，同时避免重新建设完整多模态、复杂 Agent 和多企业平台分支。
