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
用户输入 → 复杂度分类 → 路由决策 → 执行 → 结果整合 → 质量评估
              ↓           ↓
        四级分类      Plan/执行
                    ↓
              子任务并行执行
```

- **自适应推理路由**：根据问题复杂度自动选择推理策略（Simple/RAG/CoT/ReAct）
- **Plan-Execute-Reflect**：三阶段 Agent 工作流，支持多任务拆解
- **工具调用系统**：支持检索、问答、纪要生成、待办抽取等多种工具
- **人机协作**：支持人工确认机制，处理高风险操作

### 🔍 多路召回 RAG 系统

```
查询 → 三路召回 → RRF融合 → Reranker精排 → 最终结果
       ↓
  ├─ BM25（关键词检索）
  ├─ BGE-M3稠密（语义向量）
  └─ BGE-M3稀疏（lexical_weights）
```

- **三路召回**：BM25 + BGE-M3稠密 + BGE-M3稀疏向量
- **RRF融合**：Reciprocal Rank Fusion 算法融合多路召回结果
- **Reranker精排**：BGE-Reranker-v2-m3 对结果进行精排
- **知识图谱增强**：实体/关系抽取，图谱扩展检索结果
- **SPEAKER_AWARE_HYBRID 分块**：说话人感知的混合分块策略
- **RAGAS 评估**：Faithfulness、Answer Relevancy、Context Precision 等 6 项指标

### 🧠 四级复杂度分类

| 等级 | 区间 | 特点 | 策略 |
|------|------|------|------|
| S (Simple) | 0.0-0.3 | 单事实、无需检索、无推理 | 直接回答 |
| R (Retrieval) | 0.3-0.5 | 事实型、简单、需查资料 | RAG单轮检索 |
| C (CoT) | 0.5-0.75 | 需要1-2步推理 | 思维链推理 |
| A (Agent/ReAct) | 0.75-1.0 | 多跳、多源、需多轮 | ReAct多轮推理 |

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
| 向量检索 | BM25 + BGE-M3 (稠密+稀疏) + BGE-Reranker |
| 缓存 | Redis |
| 消息队列 | RabbitMQ + aio-pika |
| 异步任务 | Redis 任务状态追踪 + Worker 消费 |
| Agent 框架 | LangGraph + 自定义状态机 |
| 评估体系 | RAGAS |
| 前端框架 | Vue 3 + Vite + Element Plus + Pinia |
| 文档解析 | pdfplumber + python-docx |
| 监控 | Prometheus + Grafana |

---

## 📁 项目架构

```
meetingmind-agent/
├── backend/
│   ├── app/
│   │   ├── agents/                 # Agent 核心模块
│   │   │   ├── agent_service.py    # Agent 服务
│   │   │   ├── tools/              # 工具系统
│   │   │   ├── memory.py           # 记忆机制
│   │   │   └── prompts.py          # Prompt模板
│   │   ├── services/               # 业务服务层
│   │   │   ├── enhanced_retrieval_fusion.py  # 三路召回融合
│   │   │   ├── complexity_classifier.py      # 复杂度分类器
│   │   │   ├── rag_service.py                # RAG服务
│   │   │   └── llm_service.py                # LLM服务
│   │   ├── core/                    # 核心组件
│   │   ├── api/v1/endpoints/        # API 接口
│   │   ├── models/                  # 数据模型
│   │   ├── schemas/                 # 数据模式
│   │   └── db/                      # 数据库配置
│   ├── tests/                       # 测试目录
│   ├── model/                       # 本地模型文件
│   └── requirements.txt
│
├── frontend/                        # Vue 3 前端
│   └── src/
│       ├── views/                   # 页面组件
│       ├── api/                     # 接口封装
│       ├── stores/                  # 状态管理
│       └── components/              # 公共组件
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
| **异步任务处理** | 文档解析/向量化异步执行 | RabbitMQ + Redis 状态追踪 |
| **RAG评估** | 6项 RAGAS 指标评估 | Faithfulness、Relevancy、Precision 等 |
| **回归测试** | 性能基准测试和回归检测 | 基准建立 + 差异对比 |
| **自适应推理** | 根据问题复杂度选择推理策略 | 四级分类 + Plan模式 |

---

## 🚀 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+（建议安装 pgvector 扩展）
- Redis 6+（可选，用于缓存）
- 模型文件：BGE-M3、BGE-Reranker-v2-m3（放置于 `backend/model/`）

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
| 检索 Recall | 86.1% | 三路召回 + RRF融合后 |
| 系统延迟 | < 3s | 端到端响应时间 |
| 支持工具数 | 5+ | 会议专用工具 |
| RAGAS 指标 | 6 项 | 完整评估体系 |
| 测试数据集 | 263 题 | 覆盖各类场景 |

---

## 💡 面试亮点

1. **RAG 优化**：三路召回（BM25 + BGE-M3稠密 + BGE-M3稀疏）+ RRF融合 + Reranker精排
2. **自适应推理**：四级复杂度分类（S/R/C/A）+ Plan模式处理多任务
3. **Agent 架构**：完整的工具调用系统、状态管理、人机协作机制
4. **工程实践**：异步架构、统一异常处理、配置中心、SSE 流式输出
5. **评估体系**：RAGAS 6 项指标 + 回归测试框架 + Bad Case 分析闭环
6. **知识图谱**：实体/关系抽取集成到检索流程，提升上下文相关性
7. **异步任务处理**：RabbitMQ 消息队列 + Redis 任务状态追踪，支持文档解析、向量化等耗时任务异步执行
8. **全栈能力**：完整的前后端实现，API 设计规范

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

### 任务队列接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/tasks/documents` | POST | 创建文档处理任务 |
| `/api/v1/tasks/{task_id}` | GET | 获取任务状态 |
| `/api/v1/tasks/` | GET | 获取任务列表 |
| `/api/v1/tasks/{task_id}` | DELETE | 取消/删除任务 |

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
ENABLE_KNOWLEDGE_GRAPH=false  # 可选增强，默认不进入正式 RAG 主链路

# 复杂度分类阈值
COMPLEXITY_SIMPLE=0.3
COMPLEXITY_RETRIEVAL=0.5
COMPLEXITY_COT=0.75

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

# 运行单元测试
pytest tests/unit/ -v

# 运行 Agent 测试
pytest tests/agent/ -v

# 运行分块测试
pytest tests/chunking/ -v

# 运行检索策略对比测试
pytest tests/experiments/test_retrieval_strategy.py -v
```

---

## 📄 License

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

*项目已完成核心功能开发，包含完整的 RAG 系统、Agent 框架、自适应推理路由和前后端实现，适合作为 AI 应用开发学习和实践项目。*

```bash
# 后端启动命令
cd backend
conda activate meetingmind
python run.py

# 前端启动命令
cd frontend
npm run dev
```
netstat -ano | findstr :8000
taskkill /F /PID 19504 /T
