# MeetingMind — 会议智能助手

基于 RAG + Agent 的全流程会议管理系统，覆盖会议记录、智能摘要、知识库检索、待办跟踪等核心场景。适合中小厂Agent实习岗面试项目。

---

## 目录结构

```
meetingmind/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口，注册中间件、路由、异常处理
│   │   ├── api/v1/
│   │   │   ├── router.py       # 路由聚合
│   │   │   └── endpoints/      # 各资源接口
│   │   │       ├── users.py    # 用户注册/登录/信息
│   │   │       ├── meetings.py # 会议 CRUD + 发言记录
│   │   │       ├── documents.py# 文档上传/管理
│   │   │       └── todos.py    # 待办 CRUD + 统计
│   │   ├── agents/             # Agent相关（新增）
│   │   │   ├── prompts.py      # Prompt模板系统
│   │   │   ├── errors.py       # 错误恢复系统
│   │   │   ├── monitor.py      # 监控系统
│   │   │   └── agent_service.py# Agent服务
│   │   ├── core/
│   │   │   ├── config.py       # 环境变量配置（pydantic-settings）
│   │   │   ├── security.py     # JWT 签发/验证、密码哈希
│   │   │   ├── deps.py         # FastAPI 依赖注入（当前用户）
│   │   │   ├── response.py     # 统一响应格式 Response / PageResponse
│   │   │   ├── exceptions.py   # AppException + 全局异常处理器
│   │   │   ├── logger.py       # loguru 日志配置
│   │   │   └── cache.py        # Redis 缓存管理（连接/读写/失效）
│   │   ├── db/
│   │   │   └── database.py     # SQLAlchemy async engine + get_db
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   │   ├── user.py         # 用户表
│   │   │   ├── meeting.py      # 会议主表 + 发言记录表
│   │   │   ├── document.py     # 文档库表
│   │   │   ├── todo.py         # 待办表
│   │   │   └── vector.py       # 向量知识库表
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── services/           # 业务逻辑层
│   │   │   ├── user_service.py
│   │   │   ├── meeting_service.py
│   │   │   ├── document_service.py
│   │   │   └── todo_service.py
│   │   └── utils/              # 工具函数
│   │       └── cache_utils.py  # 缓存装饰器与辅助函数
│   ├── uploads/                # 本地文件存储目录
│   ├── logs/                   # 日志输出目录
│   ├── .env                    # 环境变量（本地，不提交，未提供则使用 core/config.py 默认值）
│   ├── requirements.txt
│   └── run.py                  # 启动入口
│
└── frontend/                   # Vue 3 前端
    ├── src/
    │   ├── main.js             # 应用入口
    │   ├── App.vue
    │   ├── router/index.js     # Vue Router 路由配置
    │   ├── api/                # Axios 请求封装
    │   │   ├── request.js      # 拦截器、token 注入
    │   │   ├── agents.js       # Agent 普通/流式查询
    │   │   ├── meetings.js
    │   │   ├── users.js
    │   │   ├── todos.js
    │   │   └── documents.js
    │   ├── stores/             # Pinia 状态管理
    │   │   ├── user.js         # 登录态、用户信息
    │   │   ├── meeting.js      # 会议列表、详情缓存
    │   │   ├── todo.js         # 待办列表 + 统计
    │   │   └── document.js     # 文档列表
    │   ├── components/
    │   │   └── layout/
    │   │       └── AppLayout.vue  # 侧边栏 + 顶栏布局
    │   └── views/              # 页面组件
    │       ├── LoginPage.vue   # 登录/注册
    │       ├── MeetingList.vue # 会议列表（搜索/分页/筛选）
    │       ├── MeetingUpload.vue # 新建会议 + 文件上传
    │       ├── MeetingDetail.vue # 会议详情 + 发言记录 + 待办
    │       ├── MeetingEdit.vue # 编辑会议
    │       ├── TodoList.vue    # 全局待办（筛选/统计/批量操作）
    │       ├── DocumentList.vue# 文档库（上传/管理/预览）
    │       ├── QueryPage.vue   # RAG 智能查询
    │       ├── AgentDemo.vue   # Agent 任务规划、执行、反思演示
    │       ├── EvaluationPage.vue # RAG 评估
    │       ├── ConfigPage.vue  # 系统配置
    │       └── ProfilePage.vue # 个人信息
    ├── vite.config.js          # Vite 配置（/api 代理到后端 8000）
    └── package.json
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.115 + Uvicorn |
| 数据库 | PostgreSQL（asyncpg）+ SQLAlchemy 2.0 async |
| 向量检索 | 文本向量 JSON/ARRAY 存储 + Python 相似度检索，支持 BM25 + 向量多路召回 + rerank |
| 数据验证 | Pydantic v2 |
| 认证 | JWT（python-jose） + bcrypt |
| 日志 | loguru（按日滚动） |
| LLM/Agent | OpenAI 兼容接口 + LangGraph |
| 前端框架 | Vue 3 + Vite |
| UI 组件 | Element Plus |
| 状态管理 | Pinia |
| 路由 | Vue Router 4 |
| HTTP 客户端 | Axios；Agent SSE 流式接口使用 Fetch |

---

## 核心特性

### RAG系统
- 支持按说话人分层切片的语义切分，提升上下文相关性
- 可配置的切分模式（speaker/fixed）
- 支持文档解析与向量化
- 向量检索与相似度匹配
- 支持 BM25 + 向量检索 + rerank 的多路召回
- 提供 RAG 评估数据集与评估接口

### Agent系统
- 基于LangGraph的 Plan-Execute-Reflect 工作流
- 工具调用系统
- 会话记忆机制（短期+长期+Checkpoint；当前主要为进程内会话记忆）
- Prompt模板系统
- 错误恢复与监控机制
- 支持 SSE 流式输出执行过程
- 支持任务模板、计划验证、计划自动修复和人机确认接口

---

## 数据库表设计

| 表名 | 说明 |
|------|------|
| `users` | 用户表（用户名、邮箱、密码哈希、部门、角色） |
| `meetings` | 会议主表（标题、状态、原文、摘要、纪要、关键词） |
| `speech_records` | 发言记录表（关联会议、发言人、时间偏移） |
| `documents` | 文档库表（文件路径、解析内容、关联会议） |
| `todo_items` | 待办表（标题、负责人、优先级、状态、截止时间） |
| `vector_chunks` | 向量知识库表（文本片段、向量、元数据） |

---

## 接口概览

所有接口统一前缀 `/api/v1`，响应格式：

```json
{ "code": 200, "message": "success", "data": {} }
```

分页响应额外包含 `total`、`page`、`page_size`、`total_pages`。

| 模块 | 主要接口 |
|------|---------|
| 用户 | `POST /users/register` `POST /users/login` `GET /users/me` |
| 会议 | `GET/POST /meetings` `GET/PUT/DELETE /meetings/{id}` |
| 文档 | `GET /documents` `POST /documents/upload` `DELETE /documents/{id}` |
| 待办 | `GET/POST /todos` `GET /todos/stats` |
| 向量检索 | `POST /vector-search/search` |
| 嵌入 | `POST /embedding/encode` |
| RAG | `POST /rag/ask` |
| 评估 | `GET /evaluation/dataset` `POST /evaluation/evaluate` `POST /evaluation/evaluate-all` |
| 配置 | `GET /config/all` `GET /config` `POST /config/{key}` |
| Agent | `POST /agents/query` `POST /agents/query-stream` `POST /agents/batch` `GET /agents/tools` `GET /agents/prompts` |

完整接口文档启动后访问：`http://localhost:8000/docs`

---

## 快速启动

### 前置条件

- Python 3.11+（推荐 conda）
- Node.js 18+

### 1. 启动后端

```bash
# 创建并激活 conda 环境（首次）
conda create -n meetingmind python=3.11 -y
conda activate meetingmind

cd backend
pip install -r requirements.txt

# 如需覆盖默认配置，创建 backend/.env 并设置 DATABASE_URL、LLM_API_KEY 等

python run.py
```

数据库表在首次启动时自动创建。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

前端通过 Vite proxy 将 `/api` 请求转发到 `http://localhost:8000`，无需额外跨域配置。

---

## 项目状态

### 已完成
- ✅ 工程架构搭建（FastAPI + Vue3）
- ✅ 基础CRUD功能（用户、会议、文档、待办）
- ✅ 基础RAG系统（向量化、检索）
- ✅ 按说话人分层切片功能
- ✅ 多路召回（BM25 + 向量检索 + rerank）与 RAG 评估接口
- ✅ Agent系统基础框架
- ✅ 记忆机制（短期+长期+Checkpoint）
- ✅ Prompt模板系统
- ✅ 错误恢复与监控系统
- ✅ 工具调用系统
- ✅ Agent 流式执行过程输出

### 优化方向
- 优化响应速度
- 完善用户交互
- 增加真实页面和接口集成测试
- 优化评估数据集与评估报告
- 将 Agent 记忆、确认请求等进程内状态持久化或按用户隔离

---

## 启动代码

```bash
# 后端
cd backend
conda activate meetingmind
python run.py

# 前端
cd frontend
npm run dev
```

---
