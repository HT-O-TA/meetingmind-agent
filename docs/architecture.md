# MeetingMind 项目目录结构

---

## 根目录

```
meetingmind-agent/
├── backend/                # 后端服务（FastAPI）
├── frontend/               # 前端服务（Vue3）
├── docs/                   # 项目文档
├── monitoring/             # 监控配置（Prometheus/Grafana）
├── .github/                # GitHub 配置（CI/CD）
├── .vscode/                # VS Code 配置
├── .pytest_cache/          # pytest 缓存
├── .gitignore              # Git忽略配置
├── .env.example            # 环境变量示例（根目录）
├── docker-compose.yml       # Docker Compose开发环境配置
├── docker-compose.prod.yml  # Docker Compose生产环境配置
├── start-docker.ps1         # Docker启动脚本
└── README.md               # 项目说明
```

---

## 后端目录 `backend/`

```
backend/
├── app/              # 应用主目录
├── tests/            # 测试目录
├── model/            # 本地模型文件（BGE-M3、Reranker等）
├── scripts/          # 辅助脚本（数据导入、向量化等）
├── .dockerignore     # Docker忽略配置
├── .env              # 环境变量（运行时）
├── .env.example      # 环境变量示例
├── Dockerfile        # Docker镜像构建配置
├── pytest.ini        # pytest配置
├── requirements.txt  # Python依赖
├── run.py            # 启动入口
├── agent_monitor.log # Agent监控日志
└── .pytest_cache/    # pytest缓存
```

### `backend/app/` 应用核心

```
app/
├── main.py           # 【入口】FastAPI应用创建、中间件注册、路由挂载、启动初始化
├── __init__.py
└── __pycache__/      # Python编译缓存
```

#### `app/agents/` Agent系统

```
agents/
├── __init__.py            # 模块初始化
├── agent_service.py       # 【核心】Agent主服务，处理用户查询、协调工作流
├── graph.py              # 【工作流】状态图（Plan-Execute-Reflect + Tool Calling）
├── nodes.py              # 【节点】Plan/Execute/Reflect 各阶段节点实现
├── state.py              # 【状态】AgentState 状态定义
├── memory.py             # 【记忆】会话记忆管理（短期/长期）
├── prompts.py            # 【Prompt】Prompt模板（支持JSON Schema验证）
├── prompt_market.py      # 【Prompt】Prompt版本管理与A/B测试
├── reflection.py         # 【反思】质量评估与结果验证
├── plan_validator.py     # 【验证】计划语法/逻辑/质量检查
├── task_templates.py     # 【模板】任务模板库，优先匹配模板
├── monitor.py            # 【监控】错误恢复、性能监控、日志记录
├── human_in_the_loop.py  # 【人机】确认请求、协作消息
├── agent_communication.py# 【通信】Agent间消息传递
├── multi_agent.py        # 【多Agent】多Agent协作框架
├── trace_integration.py  # 【追踪】LangSmith等追踪系统集成
├── errors.py             # 【异常】Agent专用异常定义
├── __pycache__/          # Python编译缓存
├── tools/                # 【工具系统】
│   ├── __init__.py       # 模块初始化
│   ├── registry.py       # 工具注册表
│   ├── manager.py        # 工具管理器
│   ├── executor.py       # 工具执行器
│   ├── selector.py       # 工具选择器
│   ├── builtin.py        # 内置工具列表
│   ├── meeting_tools.py  # 会议专用工具（问答/纪要/待办/争议）
│   ├── custom_manager.py # 自定义工具管理
│   ├── tool_metadata.py  # 工具元数据定义
│   ├── base.py           # 工具基类
│   ├── decorator.py      # 工具注册装饰器
│   ├── autocomplete.py   # 工具自动补全
│   ├── examples.py       # 工具使用示例
│   ├── policy.py         # 工具使用策略
│   ├── enterprise_tools.py # 企业级工具
│   ├── dynamic_tool_discovery.py # 动态工具发现
│   └── __pycache__/      # Python编译缓存
└── mcp/                 # 【MCP服务】Model Context Protocol
    ├── __init__.py       # 模块初始化
    ├── server.py         # MCP服务端实现
    ├── client.py         # MCP客户端
    ├── initializer.py    # MCP初始化
    ├── mcp_tool_manager.py # MCP工具管理器
    ├── __pycache__/      # Python编译缓存
    └── external_services/ # 外部企业服务MCP适配
        ├── __init__.py
        ├── feishu_server.py
        ├── github_server.py
        ├── jira_server.py
        └── notion_server.py
```

#### `app/api/` API层

```
api/
├── v1/                # API版本1
│   ├── router.py             # 【路由聚合】挂载所有endpoints
│   ├── __init__.py
│   ├── __pycache__/          # Python编译缓存
│   └── endpoints/
│       ├── users.py          # 【用户】登录/注册/用户管理
│       ├── meetings.py       # 【会议】会议CRUD/上传/解析
│       ├── documents.py      # 【文档】文档上传/解析/管理
│       ├── todos.py          # 【待办】待办CRUD/状态更新
│       ├── rag.py            # 【RAG】问答接口
│       ├── agents.py         # 【Agent】Agent查询/SSE流式输出
│       ├── vector_search.py  # 【向量检索】检索测试/状态查询
│       ├── embedding.py      # 【向量化】向量化测试/状态查询
│       ├── evaluation.py     # 【评估】RAG评估数据集/评估执行
│       ├── text_process.py   # 【文本处理】切分测试
│       ├── config.py         # 【配置】配置中心接口
│       ├── templates.py      # 【模板】任务模板管理
│       ├── tests.py          # 【测试】测试接口
│       ├── collaboration.py  # 【协作】协作消息接口
│       ├── tasks.py          # 【任务队列】异步任务创建/状态查询
│       ├── graph.py          # 【知识图谱】图查询接口
│       ├── feedback.py       # 【反馈】用户反馈管理
│       ├── mcp.py            # 【MCP】MCP服务接口
│       ├── memory.py         # 【记忆】记忆管理接口
│       ├── multi_agent.py    # 【多Agent】多Agent协作接口
│       ├── performance.py    # 【性能】性能指标接口
│       ├── reflection.py     # 【反思】反思系统接口
│       ├── trace.py          # 【追踪】追踪接口
│       ├── workflow.py       # 【工作流】工作流接口
│       ├── dynamic_tool.py   # 【动态工具】动态工具接口
│       ├── frontend_events.py # 【前端事件】前端事件推送
│       ├── cost.py           # 【成本】成本管理接口
│       ├── __init__.py
│       └── __pycache__/      # Python编译缓存
├── __init__.py
└── __pycache__/          # Python编译缓存
```

#### `app/core/` 核心模块

```
core/
├── __init__.py            # 模块初始化
├── config.py             # 【配置】Settings类，所有环境变量定义
├── config_center.py      # 【配置中心】动态配置/热更新/多源配置
├── security.py           # 【安全】JWT/密码哈希/权限控制/数据脱敏
├── logger.py             # 【日志】日志配置与格式化
├── middleware.py         # 【中间件】访问日志中间件
├── exceptions.py         # 【异常】AppException及异常处理器
├── response.py           # 【响应】统一响应格式
├── api_response.py       # 【响应】API响应封装
├── cache.py              # 【缓存】缓存接口（Redis/内存降级）
├── cache_init.py         # 【缓存】Redis连接初始化/LLM缓存/限流
├── deps.py               # 【依赖注入】get_current_user/get_db
├── dependencies.py       # 【依赖注入】其他依赖
├── fault_tolerance.py    # 【容错】重试/降级/熔断
├── observability.py      # 【可观测】指标收集/追踪
├── rabbitmq.py           # 【RabbitMQ】连接管理器，支持连接池和重连
├── __init__.py
└── __pycache__/          # Python编译缓存
```

#### `app/db/` 数据库

```
db/
├── __init__.py            # 模块初始化
└── database.py           # 【数据库】SQLAlchemy async engine/会话管理
```

#### `app/models/` ORM模型

```
models/
├── __init__.py            # 模块初始化
├── user.py               # 【用户模型】User表
├── meeting.py            # 【会议模型】Meeting/SpeechRecord表
├── document.py           # 【文档模型】Document表
├── todo.py               # 【待办模型】TodoItem表
├── vector.py             # 【向量模型】VectorChunk表
├── config.py             # 【配置模型】Config表
├── feedback.py           # 【反馈模型】Feedback表
└── __pycache__/          # Python编译缓存
```

#### `app/schemas/` Pydantic模型

```
schemas/
├── __init__.py            # 模块初始化
├── user.py               # 【用户】User请求/响应模型
├── meeting.py            # 【会议】Meeting请求/响应模型
├── document.py           # 【文档】Document请求/响应模型
├── todo.py               # 【待办】Todo请求/响应模型
├── agent.py              # 【Agent】Agent请求/响应模型
├── text_process.py       # 【文本处理】切分请求/响应模型
└── __pycache__/          # Python编译缓存
```

#### `app/services/` 业务服务

```
services/
├── __init__.py              # 模块初始化
├── llm_service.py           # 【LLM】OpenAI兼容接口调用
├── embedding_service.py     # 【向量化】BGE-M3文本向量化（稠密+稀疏）
├── vector_search_service.py # 【向量检索】pgvector/轻量模式检索
├── bm25_retriever.py       # 【BM25】BM25全文检索
├── multi_retrieval_fusion.py # 【融合】BM25+向量+Rerank多路召回融合（旧版）
├── enhanced_retrieval_fusion.py # 【增强融合】三路召回（BM25+BGE-M3稠密+BGE-M3稀疏）+ RRF融合 + Reranker精排
├── reranker.py             # 【重排序】BGE-Reranker精排
├── rag_service.py          # 【RAG】问答服务，整合检索+生成
├── rag_evaluation_service.py # 【评估】RAGAS评估/检索指标/生成指标
├── ragas_evaluator.py      # 【评估】RAGAS指标计算
├── rag_regression.py       # 【回归测试】基准对比/回归检测
├── document_service.py     # 【文档】上传/解析/切分/向量化
├── document_parser.py      # 【解析】PDF/DOCX/Excel解析
├── text_process_service.py # 【文本处理】speaker解析/固定切分
├── semantic_chunker.py     # 【语义切分】SPEAKER_AWARE_HYBRID策略，说话人感知+语义连贯性
├── meeting_service.py      # 【会议】会议CRUD/解析
├── todo_service.py         # 【待办】待办CRUD
├── user_service.py         # 【用户】用户CRUD/认证
├── knowledge_graph.py      # 【知识图谱】实体关系抽取/图谱增强检索
├── query_optimizer.py      # 【查询优化】Query改写/扩展
├── adaptive_prompt.py      # 【自适应Prompt】根据场景选择Prompt
├── complexity_classifier.py # 【复杂度分类】四级复杂度分类器（Simple/Retrieval/CoT/Agent）
├── batch_embedding.py      # 【批量向量化】批量处理优化
├── multimodal.py           # 【多模态】Vision/Whisper服务
├── cost_manager.py         # 【成本管理】推理成本统计与优化
├── performance_metrics.py  # 【性能指标】系统性能监控
├── feedback_service.py     # 【反馈服务】用户反馈收集与处理
├── long_term_memory.py     # 【长期记忆】长期记忆管理
├── task_queue.py           # 【任务队列】异步任务管理
├── agent_benchmark.py      # 【基准测试】Agent基准测试数据集与测试器
├── dspy_rag.py             # 【DSPy】DSPy优化RAG管道
├── neo4j_client.py         # 【Neo4j】Neo4j图数据库客户端
├── __init__.py
└── __pycache__/            # Python编译缓存
```

#### `app/utils/` 工具

```
utils/
├── __init__.py        # 模块初始化
├── cache_utils.py     # 【缓存工具】缓存辅助函数
└── __pycache__/       # Python编译缓存
```

#### `app/workers/` 异步任务 Worker

```
workers/
├── __init__.py           # 模块初始化
└── document_worker.py    # 【文档处理】文档解析、向量化、知识图谱构建 Worker
```

#### `app/workflows/` 工作流

```
workflows/
├── __init__.py
├── enterprise_workflow.py # 【企业工作流】企业级业务流程定义
└── __pycache__/          # Python编译缓存
```

### `backend/model/` 本地模型

```
model/
├── bge-m3/                # BGE-M3嵌入模型（稠密+稀疏）
│   ├── pytorch_model.bin
│   ├── tokenizer.json
│   ├── config.json
│   ├── onnx/              # ONNX量化版本
│   └── ...
├── bge-reranker-v2-m3/    # BGE-Reranker重排序模型
│   ├── model.safetensors
│   └── ...
├── qwen3-0.6B/            # Qwen3-0.6B复杂度分类器
│   ├── model.safetensors
│   └── ...
├── all-MiniLM-L6-v2/      # MiniLM嵌入模型（备用）
│   ├── pytorch_model.bin
│   └── ...
└── paraphrase-multilingual-MiniLM-L12-v2/  # 多语言嵌入模型（备用）
    ├── pytorch_model.bin
    └── ...
```

### `backend/scripts/` 辅助脚本

```
scripts/
├── load_test.py           # 负载测试脚本
├── feedback_loop_demo.py  # 反馈循环演示
├── migrate_graph.py       # 知识图谱迁移
├── vectorize_docs.py      # 文档向量化脚本
├── import_meeting_docs.py # 会议文档导入
└── batch_upload_docs.py   # 批量文档上传
```

### `backend/tests/` 测试

```
tests/
├── __init__.py           # 模块初始化
├── conftest.py           # pytest配置钩子
├── test_benchmark_metrics.py  # 基准测试指标计算脚本
├── test_dynamic_tool_reflection.py  # 动态工具反思测试
├── test_external_mcp_services.py    # 外部MCP服务测试
├── test_graph_api.py     # 图谱API测试
├── test_graph_api_requests.py # 图谱API请求测试
├── test_memory_multi_agent.py # 多Agent记忆测试
├── __pycache__/          # Python编译缓存
├── unit/                # 单元测试（原子级功能）
│   ├── __init__.py
│   ├── test_errors.py              # 异常处理测试
│   ├── test_state.py               # 状态机测试
│   ├── test_memory.py              # 记忆模块测试
│   ├── test_monitor.py             # 监控模块测试
│   ├── test_document_parser.py     # 文档解析测试
│   ├── test_tool_calling.py        # 工具调用测试
│   └── test_security_regressions.py # 安全回归测试
├── integration/         # 集成测试（模块间协作）
│   ├── __init__.py
│   ├── test_agent_pipeline.py      # Agent管道测试
│   └── test_rag_pipeline.py        # RAG管道测试
├── agent/               # Agent功能测试
│   ├── __init__.py
│   ├── test_agent_behavior.py      # Agent行为测试
│   ├── test_agent_workflow.py      # Agent工作流测试
│   ├── test_meeting_tools.py       # 会议工具测试
│   ├── test_tool_executor.py       # 工具执行器测试
│   ├── test_tool_manager.py        # 工具管理器测试
│   └── test_workflow_router.py     # 工作流路由测试
├── chunking/            # 分块策略测试
│   ├── __init__.py
│   ├── test_semantic_chunker.py    # 语义分块器测试
│   ├── test_document_chunking.py   # 文档切分测试
│   └── data/                       # 测试数据
│       ├── meeting_docs_plain/     # 纯文本会议文档（217个）
│       └── meeting_docs_with_speaker/  # 带说话人会议文档（217个）
├── rag/                 # RAG测试
│   ├── __init__.py
│   └── rag_eval_dataset.py         # RAG评估数据集
├── services/            # 服务层测试
│   ├── __init__.py
│   ├── test_knowledge_graph.py     # 知识图谱测试
│   ├── test_rag_regression.py      # RAG回归测试
│   └── test_ragas_evaluator.py     # RAGAS评估器测试
├── api/                 # API测试
│   ├── __init__.py
│   └── test_endpoints.py           # API端点测试
├── load/                # 负载测试
│   ├── __init__.py
│   ├── locustfile.py               # Locust压测脚本
│   └── run_load_test.py            # 压测运行脚本
├── fault/               # 容错测试
│   ├── __init__.py
│   └── test_degradation.py         # 降级策略测试
├── index_comparison/    # 索引对比测试
│   ├── __init__.py
│   └── test_index_comparison.py    # 索引性能对比
├── experiments/         # 实验测试
│   └── __init__.py
└── results/             # 测试结果
    └── 1.md
```

---

## 前端目录 `frontend/`

```
frontend/
├── src/               # 源码目录
├── dist/              # 构建产物
├── test-report/       # 测试报告目录
├── node_modules/      # npm依赖
├── index.html         # HTML入口
├── package.json       # npm依赖配置
├── package-lock.json  # npm依赖锁定
├── vite.config.js     # Vite配置
├── vitest.config.ts   # Vitest测试配置
└── Dockerfile         # Docker镜像构建配置
```

### `frontend/src/` 源码

```
src/
├── main.js            # 【入口】Vue应用创建
├── App.vue           # 【根组件】应用根组件
```

#### `src/api/` API封装

```
api/
├── request.js         # 【基础】Axios封装
├── users.js          # 【用户API】登录/注册/用户管理
├── meetings.js       # 【会议API】会议CRUD
├── documents.js      # 【文档API】文档上传/管理
├── todos.js          # 【待办API】待办CRUD
├── rag.js            # 【RAG API】问答接口
├── agents.js         # 【Agent API】Agent查询（SSE）
├── agent.ts          # 【Agent API】Agent TypeScript封装
├── vectorSearch.js   # 【向量检索API】检索测试
├── embedding.js      # 【向量化API】向量化测试
├── graph.js          # 【图谱API】图谱查询
├── feedback.js       # 【反馈API】反馈管理
├── tasks.js          # 【任务API】任务队列
└── trace.js          # 【追踪API】追踪接口
```

#### `src/router/` 路由

```
router/
└── index.js           # 【路由】Vue Router配置
```

#### `src/stores/` 状态管理

```
stores/
├── user.js            # 【用户状态】登录态/用户信息
├── meeting.js         # 【会议状态】会议数据
├── document.js        # 【文档状态】文档数据
└── todo.js            # 【待办状态】待办数据
```

#### `src/views/` 页面

```
views/
├── LoginPage.vue      # 【登录页】用户登录
├── UserList.vue       # 【用户列表】用户管理
├── MeetingList.vue    # 【会议列表】会议管理
├── MeetingDetail.vue  # 【会议详情】会议查看
├── MeetingEdit.vue    # 【会议编辑】会议编辑
├── MeetingUpload.vue  # 【会议上传】会议上传
├── DocumentList.vue   # 【文档列表】文档管理
├── TodoList.vue       # 【待办列表】待办管理
├── QueryPage.vue      # 【问答页】RAG问答
├── AgentDemo.vue      # 【Agent页】Agent演示
├── GraphPage.vue      # 【图谱页】知识图谱可视化
├── BadCasePage.vue    # 【BadCase页】坏例分析
├── TaskQueuePage.vue  # 【任务队列页】任务管理
└── TracePage.vue      # 【追踪页】追踪查看
```

#### `src/components/` 组件

```
components/
├── layout/
│   └── AppLayout.vue  # 【布局】应用布局组件
├── SSEStreamDisplay.vue # 【SSE展示】流式输出展示
└── GraphVisualization.vue # 【图谱可视化】知识图谱渲染
```

#### `src/config/` 配置

```
config/
└── index.js           # 【配置】前端配置
```

#### `src/utils/` 工具

```
utils/
└── frontendLogger.js  # 【前端日志】日志工具
```

#### `src/tests/` 测试

```
tests/
├── setup.ts           # 测试环境配置
├── api/
│   └── agent.test.ts  # Agent API测试
├── components/
│   └── AgentDemo.test.ts  # Agent组件测试
├── stores/
│   └── agent.test.ts  # Agent状态测试
└── e2e/
    └── scenarios.test.ts  # E2E场景测试
```

---

## 文档目录 `docs/`

```
docs/
├── architecture.md                    # 【架构】系统架构文档（本文件）
├── api.md                            # 【API】API接口文档
├── rag评估.md                        # 【评估】RAG评估说明（含三路召回、RRF融合）
├── chunking评估.md                   # 【切分】SPEAKER_AWARE_HYBRID策略评估
├── 量化指标.md                        # 【指标】量化指标体系
├── 项目真实总结.md                    # 【总结】项目真实总结
├── 面试提问.md                        # 【面试】面试问题清单
└── 何涛-AI应用开发（AgentRAG）-简历.md # 【简历】项目相关简历
```

---

## 监控目录 `monitoring/`

```
monitoring/
├── prometheus.yml              # Prometheus配置文件
└── grafana/                    # Grafana配置
    ├── dashboards/
    │   └── meetingmind.json    # 自定义仪表盘配置
    └── provisioning/
        ├── dashboards/
        │   └── default.yml     # 仪表盘自动加载配置
        └── datasources/
            └── prometheus.yml  # 数据源配置
```

---

## GitHub配置 `.github/`

```
.github/
└── workflows/
    ├── ci.yml                  # CI流水线配置
    └── docker-publish.yml      # Docker镜像发布配置
```

---

## 核心检索架构

```
查询 → 三路召回 → RRF融合 → Reranker精排 → 最终结果
       ↓
  ├─ BM25（关键词检索）
  ├─ BGE-M3稠密（语义向量）
  └─ BGE-M3稀疏（lexical_weights）
```

## 异步任务处理架构

```
文档上传 → 创建任务 → 入队 → Worker消费 → 状态追踪 → 结果存储
              ↓
         Redis存储任务状态
              ↓
         RabbitMQ队列
              ↓
    ┌─────────┴─────────┐
    ↓                   ↓
文档处理Worker      向量化Worker
    ↓                   ↓
解析 → 分块 → 向量化 → 存储
```

## 自适应推理路由

```
用户输入 → 复杂度分类 → 路由决策
              ↓
    ├─ S(0-0.3) → Simple QA（直接回答）
    ├─ R(0.3-0.5) → RAG（单轮检索）
    ├─ C(0.5-0.75) → CoT（思维链推理）
    └─ A(0.75-1.0) → Agent（多轮推理+工具）
    
    + Plan模式：多任务检测 → 任务拆解 → 子任务路由
```

---

## 技术栈总结

| 层级 | 目录 | 主要技术 |
|------|------|----------|
| **入口** | `app/main.py` | FastAPI + Uvicorn |
| **路由** | `app/api/v1/` | RESTful API |
| **Agent** | `app/agents/` | LangGraph + 自定义状态机 |
| **MCP** | `app/agents/mcp/` | FastMCP |
| **RAG** | `app/services/` | BM25 + BGE-M3稠密+BGE-M3稀疏 + RRF融合 + Reranker |
| **分块** | `app/services/semantic_chunker.py` | SPEAKER_AWARE_HYBRID |
| **复杂度分类** | `app/services/complexity_classifier.py` | Qwen3-0.6B分类器 |
| **消息队列** | `app/core/rabbitmq.py` | RabbitMQ + aio-pika |
| **任务队列** | `app/services/task_queue.py` | Redis + RabbitMQ 状态追踪 |
| **Worker** | `app/workers/` | 异步任务消费 |
| **数据** | `app/models/` | SQLAlchemy async + PostgreSQL + pgvector |
| **前端** | `frontend/src/` | Vue3 + Pinia + Axios |
| **测试** | `backend/tests/` | pytest + pytest-asyncio + Locust |
| **监控** | `monitoring/` | Prometheus + Grafana |
| **文档** | `docs/` | Markdown |

---

## 模型配置

| 模型 | 路径 | 用途 |
|------|------|------|
| BGE-M3 | `backend/model/bge-m3` | 稠密+稀疏向量嵌入 |
| BGE-Reranker | `backend/model/bge-reranker-v2-m3` | 检索结果精排 |
| Qwen3-0.6B | `backend/model/qwen3-0.6B` | 复杂度分类器（本地） |
| all-MiniLM-L6-v2 | `backend/model/all-MiniLM-L6-v2` | 备用嵌入模型 |
| paraphrase-multilingual-MiniLM-L12-v2 | `backend/model/paraphrase-multilingual-MiniLM-L12-v2` | 多语言嵌入模型 |

## 消息队列配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| RABBITMQ_URL | AMQP连接字符串 | amqp://admin:admin123@rabbitmq:5672 |
| QUEUE_DOCUMENT_PROCESS | 文档处理队列 | document_process |
| QUEUE_VECTOR_EMBED | 向量化队列 | vector_embed |
| QUEUE_KNOWLEDGE_GRAPH | 知识图谱构建队列 | knowledge_graph |
| QUEUE_TASK_TIMEOUT | 任务过期时间（秒） | 3600 |

---

## 系统架构图

### 1. 整体系统拓扑

```mermaid
graph TB
    subgraph 用户层[用户层]
        User[用户]
        Frontend[Vue3前端]
    end
    
    subgraph API层[API网关层]
        API[FastAPI]
        Security[JWT认证]
        Cache[Redis缓存]
        RateLimit[限流/熔断]
    end
    
    subgraph 业务层[业务逻辑层]
        Agent[Agent服务]
        RAG[RAG服务]
        Doc[文档处理]
        Async[异步任务]
        Monitor[监控评估]
    end
    
    subgraph 数据层[数据层]
        PG[(PostgreSQL)]
        PGV[(pgvector)]
        Redis[(Redis)]
        RMQ[(RabbitMQ)]
        Neo4j[(Neo4j)]
    end
    
    subgraph 模型层[模型层]
        BGE[BGE-M3]
        RER[BGE-Reranker]
        QWEN[Qwen3-0.6B]
    end
    
    User --> Frontend --> API
    API --> Security
    API --> RateLimit --> Cache
    API --> Agent
    API --> RAG
    API --> Doc
    API --> Async
    API --> Monitor
    
    Agent --> PG
    Agent --> Redis
    RAG --> PGV
    RAG --> BGE
    RAG --> RER
    RER --> BGE
    Doc --> BGE
    Async --> RMQ
    RMQ --> Doc
    RAG --> Neo4j
```

### 2. Agent状态机（LangGraph 16节点）

```mermaid
graph TD
    START --> route_node
    
    route_node --> risk_node
    
    risk_node -->|需要确认| confirmation_node
    risk_node -->|不需要确认| retrieve_node
    risk_node -->|Simple| simple_qa_node
    risk_node -->|Minutes| minutes_node
    risk_node -->|Todo| todos_node
    risk_node -->|Controversy| controversy_node
    risk_node -->|Complex| plan_node
    risk_node -->|CoT| cot_node
    risk_node -->|Agent| react_node
    
    confirmation_node -->|批准| retrieve_node
    confirmation_node -->|批准+工具| execute_node
    confirmation_node -->|拒绝| validate_node
    
    retrieve_node -->|Simple/Retrieval| simple_qa_node
    retrieve_node -->|Minutes| minutes_node
    retrieve_node -->|Todo| todos_node
    retrieve_node -->|Controversy| controversy_node
    retrieve_node -->|CoT| cot_node
    retrieve_node -->|Agent| react_node
    retrieve_node -->|Complex| plan_node
    
    simple_qa_node --> validate_node
    minutes_node --> validate_node
    todos_node --> validate_node
    controversy_node --> validate_node
    
    react_node -->|成功| validate_node
    react_node -->|失败| cot_node
    cot_node -->|成功| validate_node
    cot_node -->|失败| simple_qa_node
    
    plan_node --> tool_risk_node
    tool_risk_node -->|需要确认| confirmation_node
    tool_risk_node -->|不需要确认| execute_node
    
    execute_node --> replan_node
    replan_node -->|需要重新规划| plan_node
    replan_node -->|无需重新规划| validate_node
    
    validate_node -->|验证通过| END
    validate_node -->|验证失败| repair_node
    repair_node --> validate_node
    
    END
    
    style route_node fill:#FFE4B5
    style risk_node fill:#FFB6C1
    style tool_risk_node fill:#FFB6C1
    style confirmation_node fill:#DDA0DD
    style retrieve_node fill:#98FB98
    style plan_node fill:#FFD700
    style execute_node fill:#FFA500
    style replan_node fill:#FF4500
    style simple_qa_node fill:#90EE90
    style minutes_node fill:#90EE90
    style todos_node fill:#90EE90
    style controversy_node fill:#90EE90
    style cot_node fill:#87CEEB
    style react_node fill:#DDA0DD
    style validate_node fill:#FFE4B5
    style repair_node fill:#FFB6C1
```

### 3. 四级复杂度路由

```mermaid
graph TD
    Query[用户查询] --> ComplexityClassifier[Qwen3-0.6B复杂度分类器]
    
    ComplexityClassifier -->|score < 0.3| SimpleQA[Simple QA]
    ComplexityClassifier -->|0.3 <= score < 0.5| RAG[RAG检索]
    ComplexityClassifier -->|0.5 <= score < 0.75| CoT[CoT思维链]
    ComplexityClassifier -->|score >= 0.75| Agent[Agent多轮]
    
    SimpleQA -->|直接回答| Output[输出答案]
    RAG -->|检索+回答| Output
    CoT -->|推理+检索| Output
    Agent -->|工具调用+迭代| Output
    
    Agent --> Plan[任务规划]
    Plan --> Execute[执行]
    Execute --> Reflect[反思评估]
    Reflect -->|不满意| Plan
    
    style SimpleQA fill:#90EE90
    style RAG fill:#98FB98
    style CoT fill:#87CEEB
    style Agent fill:#DDA0DD
    style ComplexityClassifier fill:#FFD700
```

### 4. Hybrid RAG检索流程

```mermaid
graph TD
    Query[用户查询] --> VectorSearch[向量语义检索]
    
    VectorSearch --> MultiRetrieval[多路召回]
    
    MultiRetrieval --> BM25[BM25关键词检索]
    MultiRetrieval --> Dense[BGE-M3稠密向量]
    MultiRetrieval --> Sparse[BGE-M3稀疏向量]
    
    BM25 --> RRF[RRF融合]
    Dense --> RRF
    Sparse --> RRF
    
    RRF --> Reranker[BGE-Reranker精排]
    
    Reranker --> KG[知识图谱增强]
    
    KG --> Context[上下文构建]
    
    Context --> LLM[LLM生成回答]
    
    LLM --> Output[最终答案]
    
    style BM25 fill:#FFE4B5
    style Dense fill:#87CEEB
    style Sparse fill:#ADD8E6
    style RRF fill:#FFD700
    style Reranker fill:#98FB98
    style KG fill:#DDA0DD
    style LLM fill:#E6E6FA
```

### 5. 异步任务处理流程

```mermaid
graph TD
    Upload[文档上传] --> TaskQueue[任务队列]
    
    TaskQueue -->|存储状态| Redis[(Redis)]
    TaskQueue -->|发布消息| RabbitMQ[(RabbitMQ)]
    
    RabbitMQ -->|document_process| DocWorker[文档处理Worker]
    RabbitMQ -->|vector_embed| VecWorker[向量化Worker]
    RabbitMQ -->|knowledge_graph| KGWorker[知识图谱Worker]
    
    DocWorker --> Parse[文档解析]
    Parse --> Chunk[语义分块]
    
    Chunk --> VecWorker
    VecWorker --> Embed[BGE-M3向量化]
    Embed --> StoreVec[(pgvector)]
    
    Embed --> KGWorker
    KGWorker --> Extract[实体关系抽取]
    Extract --> StoreKG[(Neo4j)]
    
    DocWorker -->|更新进度| Redis
    VecWorker -->|更新进度| Redis
    KGWorker -->|更新进度| Redis
    
    Redis -->|查询状态| API[API查询]
    
    style DocWorker fill:#FFA500
    style VecWorker fill:#87CEEB
    style KGWorker fill:#98FB98
```

### 6. Plan-Execute-Reflect循环

```mermaid
graph TD
    Start[开始] --> Plan[Plan阶段]
    
    Plan -->|任务分析| Decompose[任务拆解]
    Decompose -->|工具选择| ToolSelect[工具选择]
    ToolSelect -->|依赖分析| Dependency[依赖分析]
    Dependency --> PlanOutput[生成执行计划]
    
    PlanOutput --> Execute[Execute阶段]
    
    Execute -->|并行执行| Parallel[并行任务执行]
    Parallel -->|工具调用| ToolCall[工具调用]
    ToolCall -->|上下文传递| Context[上下文传递]
    Context --> ExecOutput[执行结果]
    
    ExecOutput --> Reflect[Reflect阶段]
    
    Reflect -->|准确性评估| Accuracy[准确性评估]
    Reflect -->|相关性评估| Relevance[相关性评估]
    Reflect -->|完整性评估| Completeness[完整性评估]
    Reflect -->|置信度计算| Confidence[置信度计算]
    
    Confidence -->|置信度 >= 0.7| Finish[完成]
    Confidence -->|置信度 < 0.7| Replan[重新规划]
    
    Replan --> Plan
    
    style Plan fill:#FFD700
    style Execute fill:#FFA500
    style Reflect fill:#E6E6FA
    style Replan fill:#FF4500
```

### 7. Docker部署拓扑

```mermaid
graph TD
    subgraph Docker[Docker Compose]
        subgraph Backend[后端服务]
            FastAPI[meetingmind-backend]
        end
        
        subgraph Frontend[前端服务]
            Vue[meetingmind-frontend]
        end
        
        subgraph Database[数据库层]
            PG[postgres:16]
            Redis[redis:7]
            RMQ[rabbitmq:3.13]
            Neo4j[neo4j:5.15]
        end
        
        subgraph Monitoring[监控层]
            Prometheus[prometheus:2.51]
            Grafana[grafana:10.4]
        end
    end
    
    subgraph Host[宿主机]
        HostPort8000[8000端口]
        HostPort8080[8080端口]
        HostPort5432[5432端口]
        HostPort6379[6379端口]
        HostPort5672[5672端口]
        HostPort7474[7474端口]
        HostPort9090[9090端口]
        HostPort3000[3000端口]
    end
    
    HostPort8000 --> FastAPI
    HostPort8080 --> Vue
    HostPort5432 --> PG
    HostPort6379 --> Redis
    HostPort5672 --> RMQ
    HostPort7474 --> Neo4j
    HostPort9090 --> Prometheus
    HostPort3000 --> Grafana
    
    FastAPI --> PG
    FastAPI --> Redis
    FastAPI --> RMQ
    FastAPI --> Neo4j
    
    RMQ --> FastAPI
    
    Prometheus --> FastAPI
    Grafana --> Prometheus
    
    style FastAPI fill:#98FB98
    style Vue fill:#87CEEB
    style PG fill:#FFE4B5
    style Redis fill:#FFD700
    style RMQ fill:#FFA500
    style Neo4j fill:#DDA0DD
    style Prometheus fill:#E6E6FA
    style Grafana fill:#E6E6FA
```

### 8. 记忆系统架构

```mermaid
graph TD
    subgraph 短期记忆[短期记忆（会话级）]
        SessionMemory[会话记忆]
        RedisShort[Redis 24h过期]
        Recent[N最近对话]
    end
    
    subgraph 长期记忆[长期记忆（跨会话）]
        LongTerm[长期记忆条目]
        RedisLong[Redis关键词索引]
        KG[知识图谱关联]
        Relevance[相关性评分]
        TimeDecay[时间衰减]
    end
    
    subgraph 记忆类型
        Summary[会议纪要]
        Decision[决策]
        Action[行动项]
        Topic[讨论主题]
        Knowledge[组织知识]
    end
    
    Query[用户查询] --> MemorySearch[记忆检索]
    
    MemorySearch --> SessionMemory
    SessionMemory --> RedisShort
    RedisShort --> Recent
    
    MemorySearch --> LongTerm
    LongTerm --> RedisLong
    RedisLong --> KG
    KG --> Relevance
    Relevance --> TimeDecay
    
    LongTerm --> Summary
    LongTerm --> Decision
    LongTerm --> Action
    LongTerm --> Topic
    LongTerm --> Knowledge
    
    SessionMemory --> Context[上下文构建]
    LongTerm --> Context
    
    Context --> Agent[Agent处理]
    
    Agent -->|新记忆| SessionMemory
    Agent -->|持久化| LongTerm
    
    style SessionMemory fill:#87CEEB
    style RedisShort fill:#87CEEB
    style LongTerm fill:#98FB98
    style RedisLong fill:#98FB98
    style KG fill:#DDA0DD
    style Relevance fill:#FFD700
    style TimeDecay fill:#FFD700
```

### 9. 模型路由与成本优化

```mermaid
graph TD
    Query[用户查询] --> Complexity[复杂度分类器]
    
    Complexity -->|score < 0.3| Simple[Simple]
    Complexity -->|0.3 <= score < 0.5| Retrieval[Retrieval]
    Complexity -->|0.5 <= score < 0.75| CoT[CoT]
    Complexity -->|score >= 0.75| Agent[Agent]
    
    Simple -->|qwen-turbo| LLM1[LLM调用]
    Retrieval -->|qwen-plus| LLM2[LLM调用]
    CoT -->|qwen-plus| LLM3[LLM调用]
    Agent -->|qwen-max| LLM4[LLM调用]
    
    LLM1 --> CostCalc[成本计算]
    LLM2 --> CostCalc
    LLM3 --> CostCalc
    LLM4 --> CostCalc
    
    CostCalc --> CostCompare[成本对比]
    
    CostCompare -->|固定max| FixedCost[$0.95]
    CostCompare -->|动态路由| DynamicCost[$0.39]
    
    DynamicCost --> Savings[节省59%]
    
    Savings --> Result[结果输出]
    
    style Simple fill:#90EE90
    style Retrieval fill:#98FB98
    style CoT fill:#87CEEB
    style Agent fill:#DDA0DD
    style Complexity fill:#FFD700
    style LLM1 fill:#FFE4B5
    style LLM2 fill:#FFE4B5
    style LLM3 fill:#FFE4B5
    style LLM4 fill:#FFE4B5
    style CostCalc fill:#FFA500
    style Savings fill:#90EE90
```
