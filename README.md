# MeetingMind - 会议智能 Agent 系统

基于 **RAG + Agent** 的智能会议助手，支持会议问答、纪要生成、待办抽取、争议点分析、知识图谱增强等核心功能。

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)
![Vue](https://img.shields.io/badge/Vue-3-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 🌟 核心特性

### 🤖 智能 Agent 架构

```
用户输入 → 任务规划 → 工具调用 → 结果整合 → 质量评估
              ↓            ↓            ↓           ↓
          任务拆解      并行执行       上下文管理    拒答机制
          依赖分析      状态跟踪       记忆机制      优化建议
```

- **Plan-Execute-Reflect**：三阶段 Agent 工作流
- **任务并行执行**：智能识别可并行任务，提升执行效率
- **工具调用系统**：支持检索、问答、纪要生成、待办抽取等多种工具
- **人机协作**：支持人工确认机制，处理高风险操作

### 🔍 多路召回 RAG 系统

- **BM25 + 向量检索 + Reranker**：三层检索链路
- **知识图谱增强**：实体/关系抽取，图谱扩展检索结果
- **RAGAS 评估**：Faithfulness、Answer Relevancy、Context Precision 等 6 项指标
- **回归测试框架**：完整的性能基准测试和回归检测

### 🛠️ 企业级工程化

- **异步架构**：FastAPI + SQLAlchemy 2.0 async
- **配置中心**：统一的配置管理和热更新
- **异常处理**：全局异常处理器 + 多层降级策略
- **SSE 流式输出**：实时展示 Agent 执行过程
- **监控系统**：性能指标收集、错误统计、执行追踪

---

## 📋 技术栈

| 层次 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + Uvicorn + SQLAlchemy 2.0 async |
| 数据库 | PostgreSQL (支持 pgvector) |
| 向量检索 | BM25 + BGE-M3 + BGE-Reranker |
| 缓存 | Redis |
| Agent 框架 | 自定义状态机 + 工具执行器 |
| 评估体系 | RAGAS |
| 前端框架 | Vue 3 + Vite + Element Plus + Pinia |
| 文档解析 | pdfplumber + python-docx |

---

## 📁 项目架构

```
meetingmind/
├── backend/
│   ├── app/
│   │   ├── agents/                 # Agent 核心模块
│   │   │   ├── agent_service.py    # Agent 服务
│   │   │   ├── tools/              # 工具系统
│   │   │   │   ├── meeting_tools.py # 会议专用工具
│   │   │   │   ├── executor.py     # 工具执行器
│   │   │   │   ├── manager.py      # 工具管理器
│   │   │   │   └── registry.py     # 工具注册中心
│   │   │   ├── memory.py           # 记忆机制
│   │   │   ├── monitor.py          # 监控系统
│   │   │   └── human_in_the_loop.py # 人机协作
│   │   ├── services/               # 业务服务层
│   │   │   ├── vector_search_service.py   # 向量检索
│   │   │   ├── multi_retrieval_fusion.py  # 多路召回融合
│   │   │   ├── knowledge_graph.py        # 知识图谱
│   │   │   ├── rag_service.py            # RAG服务
│   │   │   ├── ragas_evaluator.py        # RAGAS评估
│   │   │   ├── rag_regression.py         # 回归测试
│   │   │   └── llm_service.py            # LLM服务
│   │   ├── core/                    # 核心组件
│   │   │   ├── config.py            # 配置管理
│   │   │   ├── config_center.py     # 配置中心
│   │   │   ├── response.py          # 统一响应
│   │   │   └── logger.py            # 日志系统
│   │   ├── api/v1/endpoints/        # API 接口
│   │   │   ├── agents.py            # Agent接口
│   │   │   ├── rag.py               # RAG接口
│   │   │   ├── evaluation.py        # 评估接口
│   │   │   ├── meetings.py          # 会议接口
│   │   │   ├── documents.py         # 文档接口
│   │   │   └── ...
│   │   ├── models/                  # 数据模型
│   │   ├── schemas/                 # 数据模式
│   │   └── db/                      # 数据库配置
│   ├── tests/                       # 测试目录
│   │   ├── agents/                  # Agent测试
│   │   ├── services/                # 服务测试
│   │   ├── unit/                    # 单元测试
│   │   └── integration/             # 集成测试
│   └── requirements.txt
│
├── frontend/                        # Vue 3 前端
│   └── src/
│       ├── views/                   # 页面组件
│       │   ├── AgentDemo.vue        # Agent演示
│       │   ├── EvaluationPage.vue   # 评估面板
│       │   ├── ConfirmationPage.vue # 人机协作
│       │   └── ...
│       ├── api/                     # 接口封装
│       ├── stores/                  # 状态管理
│       ├── components/              # 公共组件
│       └── router/                  # 路由配置
│
└── docs/                            # 项目文档
```

---

## ✨ 核心功能

| 功能 | 描述 | 技术实现 |
|------|------|---------|
| **会议问答** | 基于 RAG 的智能问答，支持引用溯源 | BM25 + 向量 + Reranker + 知识图谱 |
| **纪要生成** | 自动生成结构化会议纪要 | LLM 生成 + 模板优化 |
| **待办抽取** | 智能识别会议中的待办事项 | 工具调用 + JSON 结构化输出 |
| **争议分析** | 识别会议中的分歧点和讨论焦点 | 多任务并行 + 结果整合 |
| **知识图谱** | 实体/关系抽取，增强检索结果 | 图谱扩展 + 上下文关联 |
| **知识库管理** | 多格式文档解析与向量化存储 | PDF/DOCX/TXT + BGE-M3 |
| **RAG评估** | 6项 RAGAS 指标评估 | Faithfulness、Relevancy、Precision 等 |
| **回归测试** | 性能基准测试和回归检测 | 基准建立 + 差异对比 |
| **混合缓存** | 三级缓存方案优化性能 | 原生 Redis + FastAPI-Cache + LLM响应缓存 |

---

## 🚀 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+（建议安装 pgvector 扩展）
- Redis 6+（可选，用于缓存）

### 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
# 创建 .env 文件，参考 .env.example 设置：
# - DATABASE_URL: 数据库连接地址
# - LLM_API_KEY: LLM API Key
# - LLM_API_BASE: LLM API 地址

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端启动

```bash
cd frontend

npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用。

---

## 📊 关键指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 检索 Recall | 86.1% | Speaker Chunking 优化后 |
| 系统延迟 | < 3s | 端到端响应时间 |
| 支持工具数 | 5+ | 会议专用工具 |
| RAGAS 指标 | 6 项 | 完整评估体系 |
| 测试数据集 | 263 题 | 覆盖各类场景 |

---

## 💡 面试亮点

1. **RAG 优化**：多路召回（BM25 + 向量 + Reranker）+ 知识图谱增强检索
2. **Agent 架构**：完整的工具调用系统、状态管理、人机协作机制
3. **工程实践**：异步架构、统一异常处理、配置中心、SSE 流式输出
4. **评估体系**：RAGAS 6 项指标 + 回归测试框架 + Bad Case 分析闭环
5. **知识图谱**：实体/关系抽取集成到检索流程，提升上下文相关性
6. **全栈能力**：完整的前后端实现，API 设计规范

---

## 📝 API 接口

### Agent 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/agents/query` | POST | Agent 问答接口 |
| `/api/v1/agents/query-stream` | POST | 流式问答接口 |
| `/api/v1/agents/confirmations/pending` | GET | 获取待确认请求 |
| `/api/v1/agents/confirmations/respond` | POST | 响应确认请求 |

### RAG 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/rag/ask` | POST | RAG 问答 |
| `/api/v1/evaluation/evaluate-all` | POST | 评估全部数据集 |
| `/api/v1/evaluation/regression` | POST | 运行回归测试 |
| `/api/v1/evaluation/baseline` | POST | 建立基准 |

### 会议接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/meetings` | GET/POST | 会议列表/创建 |
| `/api/v1/meetings/{id}` | GET/PUT/DELETE | 会议详情/更新/删除 |
| `/api/v1/todos` | GET/POST | 待办事项管理 |

---

## 🔧 配置说明

### 主要配置项

```bash
# .env 文件示例

# 数据库配置
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/meetingmind

# LLM 配置
LLM_API_KEY=your-api-key
LLM_API_BASE=https://api.example.com/v1
LLM_MODEL=qwen3.6-plus

# 向量检索配置
TOP_K_DEFAULT=5
SIMILARITY_THRESHOLD=0.5
ENABLE_KNOWLEDGE_GRAPH=true

# 安全配置
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

## 🧪 测试运行

```bash
cd backend

# 运行所有测试
pytest

# 运行指定测试
pytest tests/services/test_rag_regression.py -v

# 运行集成测试
pytest tests/integration/ -v
```

---

## 📄 License

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

*项目已完成核心功能开发，包含完整的 RAG 系统、Agent 框架、评估体系和前后端实现，适合作为 AI 应用开发学习和实践项目。*

```bash
# 后端
cd backend
conda activate meetingmind
python run.py

# 前端
cd frontend
npm run dev
```