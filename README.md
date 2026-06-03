# MeetingMind - 会议智能 Agent 系统

基于 **RAG + LangGraph Agent** 的智能会议助手，支持会议问答、纪要生成、待办抽取、争议点分析等核心功能。

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)
![Vue](https://img.shields.io/badge/Vue-3-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 核心特性

### 智能 Agent 架构

```
用户输入 → Plan Agent（任务规划）→ Execute Agent（并行执行）→ Reflect Agent（质量评估）
                ↓                        ↓                      ↓
           任务拆解                  工具调用                 结果优化
           依赖分析                 上下文传递              拒答机制
```

- **Plan-Execute-Reflect**：基于 LangGraph 的三阶段 Agent 工作流
- **任务并行执行**：智能识别可并行任务，提升执行效率
- **工具调用系统**：支持检索、问答、纪要生成、待办抽取等多种工具

### 多路召回 RAG 系统

- **BM25 + 向量检索 + BGE-Reranker**：三层检索链路
- **Speaker Chunking**：针对会议场景的发言者感知切片策略
- **RAGAS 评估**：Faithfulness、Answer Relevancy、Context Precision 等 6 项指标

### 企业级工程化

- **异步架构**：FastAPI + asyncpg + SQLAlchemy 2.0 async
- **配置中心**：统一的配置管理和热更新
- **异常处理**：全局异常处理器 + 多层降级策略
- **SSE 流式输出**：实时展示 Agent 执行过程

---

## 技术栈

| 层次 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + Uvicorn + SQLAlchemy 2.0 async |
| 数据库 | PostgreSQL + Redis |
| 向量检索 | BM25 + BGE-M3 + BGE-Reranker |
| Agent 框架 | LangGraph |
| 评估体系 | RAGAS |
| 前端框架 | Vue 3 + Vite + Element Plus + Pinia |
| 文档解析 | pdfplumber + python-docx |

---

## 项目架构

```
meetingmind/
├── backend/
│   ├── app/
│   │   ├── agents/              # Agent 核心模块
│   │   │   ├── graph.py         # LangGraph 图定义
│   │   │   ├── nodes.py         # Plan/Execute/Reflect 节点
│   │   │   ├── memory.py        # 记忆机制
│   │   │   └── tools/           # 工具系统
│   │   ├── services/            # 业务服务层
│   │   │   ├── vector_search_service.py   # 向量检索
│   │   │   ├── multi_retrieval_fusion.py  # 多路召回融合
│   │   │   ├── reranker.py      # 重排序
│   │   │   └── ragas_evaluator.py # RAGAS 评估
│   │   ├── core/                # 核心组件
│   │   └── api/                 # API 接口
│   └── requirements.txt
│
├── frontend/                     # Vue 3 前端
│   └── src/
│       ├── views/               # 页面组件
│       ├── api/                 # 接口封装
│       └── stores/              # 状态管理
│
└── docs/                        # 项目文档
    ├── architecture.md          # 架构设计
    └── api.md                   # 接口文档
```

---

## 核心功能

| 功能 | 描述 | 技术实现 |
|------|------|---------|
| **会议问答** | 基于 RAG 的智能问答，支持引用溯源 | BM25 + 向量 + Reranker 多路召回 |
| **纪要生成** | 自动生成结构化会议纪要 | LLM 生成 + 模板优化 |
| **待办抽取** | 智能识别会议中的待办事项 | 任务型 Agent + JSON 结构化输出 |
| **争议分析** | 识别会议中的分歧点和讨论焦点 | 多任务并行 + 结果整合 |
| **知识库管理** | 多格式文档解析与向量化存储 | PDF/DOCX/TXT + BGE-M3 |

---

## 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 6+（可选）

### 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选）
# 创建 .env 文件设置 DATABASE_URL、LLM_API_KEY 等

# 启动服务
python run.py
```

### 前端启动

```bash
cd frontend

npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用。

---

## 关键指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 检索 Recall | 86.1% | Speaker Chunking 优化后 |
| 系统延迟 | < 3s | 端到端响应时间 |
| 支持工具数 | 5+ | 会议专用工具 |
| RAGAS 指标 | 6 项 | 完整评估体系 |

---

## 面试亮点

1. **RAG 优化**：Speaker Chunking 策略，Recall 从 59.6% 提升至 86.1%
2. **Agent 架构**：Plan-Execute-Reflect 工作流，支持任务并行执行
3. **工程实践**：异步架构、统一异常处理、配置中心、SSE 流式输出
4. **评估体系**：RAGAS 6 项指标 + Bad Case 分析闭环
5. **工具系统**：完整的工具注册、调用、缓存机制

---

## License

MIT License
