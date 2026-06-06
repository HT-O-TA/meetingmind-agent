# MeetingMind 项目目录结构

---

## 根目录

```
meetingmind-agent/
├── backend/          # 后端服务（FastAPI）
├── frontend/         # 前端服务（Vue3）
├── docs/             # 项目文档
├── .gitignore        # Git忽略配置
└── README.md         # 项目说明
```

---

## 后端目录 `backend/`

```
backend/
├── app/              # 应用主目录
├── tests/            # 测试目录
├── .env.example      # 环境变量示例
├── pytest.ini        # pytest配置
├── requirements.txt  # Python依赖
└── run.py            # 启动入口
```

### `backend/app/` 应用核心

```
app/
├── main.py           # 【入口】FastAPI应用创建、中间件注册、路由挂载、启动初始化
├── __init__.py
```

#### `app/agents/` Agent系统

```
agents/
├── agent_service.py      # 【核心】Agent主服务，处理用户查询、协调工作流
├── graph.py             # 【工作流】状态图
├── graph_toolcalling.py  # 【工作流】Tool Calling 模式状态图
├── nodes.py             # 【节点】Plan/Execute/Reflect 各阶段节点实现
├── nodes_toolcalling.py  # 【节点】Tool Calling 模式节点实现
├── state.py             # 【状态】AgentState 状态定义
├── memory.py             # 【记忆】会话记忆管理（短期/长期）
├── prompts.py           # 【Prompt】Prompt模板
├── prompt_market.py      # 【Prompt】Prompt版本管理与A/B测试
├── reflection.py         # 【反思】质量评估与结果验证
├── plan_validator.py     # 【验证】计划语法/逻辑/质量检查
├── task_templates.py     # 【模板】任务模板库，优先匹配模板
├── monitor.py           # 【监控】错误恢复、性能监控、日志记录
├── human_in_the_loop.py # 【人机】确认请求、协作消息
├── agent_communication.py# 【通信】Agent间消息传递
├── errors.py            # 【异常】Agent专用异常定义
└── tools/               # 【工具系统】
    ├── registry.py       # 工具注册表
    ├── manager.py        # 工具管理器
    ├── executor.py       # 工具执行器
    ├── selector.py       # 工具选择器
    ├── builtin.py        # 内置工具列表
    ├── meeting_tools.py  # 会议专用工具（问答/纪要/待办/争议）
    ├── custom_manager.py # 自定义工具管理
    ├── tool_metadata.py  # 工具元数据定义
    ├── base.py           # 工具基类
    ├── decorator.py      # 工具注册装饰器
    ├── autocomplete.py   # 工具自动补全
    └── examples.py       # 工具使用示例
```

#### `app/api/v1/` API路由

```
api/v1/
├── router.py             # 【路由聚合】挂载所有endpoints
└── endpoints/
    ├── users.py          # 【用户】登录/注册/用户管理
    ├── meetings.py       # 【会议】会议CRUD/上传/解析
    ├── documents.py      # 【文档】文档上传/解析/管理
    ├── todos.py          # 【待办】待办CRUD/状态更新
    ├── rag.py            # 【RAG】问答接口
    ├── agents.py         # 【Agent】Agent查询/SSE流式输出
    ├── vector_search.py  # 【向量检索】检索测试/状态查询
    ├── embedding.py      # 【向量化】向量化测试/状态查询
    ├── evaluation.py     # 【评估】RAG评估数据集/评估执行
    ├── text_process.py   # 【文本处理】切分测试
    ├── config.py         # 【配置】配置中心接口
    ├── templates.py      # 【模板】任务模板管理
    ├── tests.py          # 【测试】测试接口
    └── collaboration.py  # 【协作】协作消息接口
```

#### `app/core/` 核心模块

```
core/
├── config.py             # 【配置】Settings类，所有环境变量定义
├── config_center.py      # 【配置中心】动态配置/热更新/多源配置
├── security.py           # 【安全】JWT/密码哈希/权限控制/数据脱敏
├── logger.py             # 【日志】日志配置与格式化
├── middleware.py         # 【中间件】访问日志中间件
├── exceptions.py         # 【异常】AppException及异常处理器
├── response.py           # 【响应】统一响应格式
├── api_response.py       # 【响应】API响应封装
├── cache.py              # 【缓存】缓存接口（Redis/内存降级）
├── cache_init.py         # 【缓存】Redis连接初始化/LLM缓存
├── deps.py               # 【依赖注入】get_current_user/get_db
├── dependencies.py       # 【依赖注入】其他依赖
├── fault_tolerance.py    # 【容错】重试/降级/熔断
└── observability.py      # 【可观测】指标收集/追踪
```

#### `app/db/` 数据库

```
db/
├── database.py           # 【数据库】SQLAlchemy async engine/会话管理
```

#### `app/models/` ORM模型

```
models/
├── user.py               # 【用户模型】User表
├── meeting.py            # 【会议模型】Meeting/SpeechRecord表
├── document.py           # 【文档模型】Document表
├── todo.py               # 【待办模型】TodoItem表
├── vector.py             # 【向量模型】VectorChunk表
└── config.py             # 【配置模型】Config表
```

#### `app/schemas/` Pydantic模型

```
schemas/
├── user.py               # 【用户】User请求/响应模型
├── meeting.py            # 【会议】Meeting请求/响应模型
├── document.py           # 【文档】Document请求/响应模型
├── todo.py               # 【待办】Todo请求/响应模型
├── agent.py              # 【Agent】Agent请求/响应模型
└── text_process.py       # 【文本处理】切分请求/响应模型
```

#### `app/services/` 业务服务

```
services/
├── llm_service.py            # 【LLM】OpenAI兼容接口调用
├── embedding_service.py      # 【向量化】BGE-M3文本向量化
├── vector_search_service.py  # 【向量检索】pgvector/轻量模式检索
├── bm25_retriever.py        # 【BM25】BM25全文检索
├── multi_retrieval_fusion.py # 【融合】BM25+向量+Rerank多路召回融合
├── reranker.py              # 【重排序】BGE-Reranker精排
├── rag_service.py           # 【RAG】问答服务，整合检索+生成
├── rag_evaluation_service.py # 【评估】RAGAS评估/检索指标/生成指标
├── ragas_evaluator.py       # 【评估】RAGAS指标计算
├── rag_regression.py        # 【回归测试】基准对比/回归检测
├── document_service.py      # 【文档】上传/解析/切分/向量化
├── document_parser.py       # 【解析】PDF/DOCX/Excel解析
├── text_process_service.py   # 【文本处理】speaker解析/固定切分
├── semantic_chunker.py      # 【语义切分】SPEAKER_AWARE_HYBRID策略，说话人感知+语义连贯性
├── meeting_service.py       # 【会议】会议CRUD/解析
├── todo_service.py          # 【待办】待办CRUD
├── user_service.py          # 【用户】用户CRUD/认证
├── knowledge_graph.py       # 【知识图谱】实体关系抽取/图谱增强检索
├── query_optimizer.py       # 【查询优化】Query改写/扩展
├── adaptive_prompt.py       # 【自适应Prompt】根据场景选择Prompt
├── batch_embedding.py       # 【批量向量化】批量处理优化
└── multimodal.py            # 【多模态】Vision/Whisper服务
```

#### `app/utils/` 工具

```
utils/
└── cache_utils.py        # 【缓存工具】缓存辅助函数
```

### `backend/tests/` 测试

```
tests/
├── agent/                # Agent测试
│   ├── test_agent_behavior.py      # Agent行为测试
│   ├── test_agent_workflow.py      # Agent工作流测试
│   ├── test_meeting_tools.py       # 会议工具测试
│   ├── test_tool_executor.py       # 工具执行器测试
│   └── test_tool_manager.py        # 工具管理器测试
├── chunking/             # 切分测试
│   ├── chunking_evaluator.py       # 切分评估器
│   ├── test_semantic_chunker.py    # 语义分块器测试
│   └── data/                       # 测试数据
│       ├── meeting_docs_plain/     # 纯文本会议文档
│       └── meeting_docs_with_speaker/  # 带说话人会议文档
└── unit/                # 单元测试
```

---

## 前端目录 `frontend/`

```
frontend/
├── src/               # 源码目录
├── index.html         # HTML入口
├── package.json       # npm依赖
├── vite.config.js     # Vite配置
└── vitest.config.ts   # Vitest测试配置
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
└── embedding.js      # 【向量化API】向量化测试
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
├── ProfilePage.vue    # 【个人页】用户信息
├── MeetingList.vue    # 【会议列表】会议管理
├── MeetingDetail.vue  # 【会议详情】会议查看
├── MeetingEdit.vue    # 【会议编辑】会议编辑
├── MeetingUpload.vue  # 【会议上传】会议上传
├── DocumentList.vue   # 【文档列表】文档管理
├── TodoList.vue       # 【待办列表】待办管理
├── QueryPage.vue      # 【问答页】RAG问答
├── AgentDemo.vue      # 【Agent页】Agent演示
├── EvaluationPage.vue # 【评估页】RAG评估
├── ConfigPage.vue     # 【配置页】配置中心
├── TestPage.vue       # 【测试页】功能测试
├── EmbeddingTest.vue  # 【向量化测试】向量化测试
├── VectorSearchTest.vue # 【检索测试】向量检索测试
└── ConfirmationPage.vue # 【确认页】人机确认
```

#### `src/components/` 组件

```
components/
└── layout/
    └── AppLayout.vue  # 【布局】应用布局组件
```

#### `src/config/` 配置

```
config/
└── index.js           # 【配置】前端配置
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
├── architecture.md    # 【架构】系统架构文档（本文件）
├── api.md            # 【API】API接口文档
├── rag评估.md        # 【评估】RAG评估说明
├── chunking评估1.md  # 【切分】切分策略评估（2x3因子实验）
├── chunking评估2.md  # 【切分】SPEAKER_AWARE_HYBRID策略评估
└── 拓展.md           # 【拓展】项目拓展计划
```

---

## 技术栈总结

| 层级 | 目录 | 主要技术 |
|------|------|----------|
| **入口** | `app/main.py` | FastAPI + Uvicorn |
| **路由** | `app/api/v1/` | RESTful API |
| **Agent** | `app/agents/` | 状态机 + Tool Calling |
| **RAG** | `app/services/` | BM25 + Vector + Rerank |
| **分块** | `app/services/semantic_chunker.py` | SPEAKER_AWARE_HYBRID |
| **数据** | `app/models/` | SQLAlchemy async |
| **前端** | `frontend/src/` | Vue3 + Pinia + Axios |
| **测试** | `backend/tests/` | pytest |
| **文档** | `docs/` | Markdown |
