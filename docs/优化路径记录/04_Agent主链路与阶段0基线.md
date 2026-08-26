# 优化路径记录 04：Agent 主链路与阶段 0 运行基线

> **历史快照**：本文的 Router、默认关闭能力和 `133 passed` 是阶段 0 时点证据。阶段 7 已直接删除 text-process、KG、MCP、Multi-Agent 等入口/框架，不再使用“默认关闭”的口径；当前测试基线见阶段 7。

**记录时间**：2026-08-26

**对应路线**：阶段 0「真实性审计与收敛」步骤 2-4

## 1. 阶段结论

阶段 0 已完成代码、配置、README 和测试口径的第一轮统一：

- 生产默认 Agent 只注册 Simple RAG 与 Plan-Execute Tool Agent；
- ReAct、CoT、深度反思、Query Rewrite、Sparse、KG、MCP、多模态和 Agent Worker 默认关闭；
- `create_agent_graph()` 是唯一图编译入口，调用方不再重复 `compile()`；
- 生产、内部、可选、退役 Router 通过独立策略表管理；
- HITL 统一为异步 pending/resume 契约，创建确认请求不再等价于批准；
- 本地复杂度模型是可选增强，未安装 Transformers 时使用规则降级；
- 核心测试从首轮 22 个失败收敛为 0 个失败。

这不是“项目全部完成”。它只证明正式边界已经可解释、核心代码能在轻量环境中导入并通过当前自动化测试。

## 2. 正式 Agent 架构

```text
POST /api/v1/agents/query
  → FastAPI 依赖注入
  → AgentService
  → 已编译的唯一 LangGraph
      → Route：任务类型 + 复杂度；本地模型不可用时规则降级
      → Prompt Injection 检查
      → 风险判断
      ├─ Simple RAG
      │   → 可选检索
      │   → 问答 / 纪要 / 待办 / 争议确定性节点
      │   → Validate / Repair
      └─ Tool Agent
          → Plan
          → Tool risk + ToolPolicy
          → 需要确认？
              ├─ 是：保存 Redis 请求与恢复快照 → 返回 pending → 本轮结束
              └─ 否：ToolExecutor
          → Replan / 统一质量门禁
          → Validate / Repair
```

批准高风险操作的恢复链路：

```text
POST /api/v1/agents/confirmations/resume
  → 读取 Redis 中的 pending 请求与恢复快照
  → 写入 approved 状态
  → 仅恢复受支持的 tool pending_action
  → ToolExecutor → Replan → Validate
```

重要安全不变量：`request_confirmation()` 返回的是 `request_id`，不是批准结果。确认状态必须先是 `pending`；只有显式批准的恢复请求才能继续高风险工具执行。

## 3. Router 暴露边界

生产环境默认入口：

- users、meetings、documents、todos；
- text-process、rag、agents、feedback、tasks。

仅 development/test 注册：

- embedding、vector-search、evaluation、config、templates；
- frontend-events、trace、performance、memory、dynamic-tool、reflection、cost。

仅显式开关注册：

- KG：`ENABLE_KNOWLEDGE_GRAPH=true`；
- MCP：`ENABLE_MCP_SERVER=true`。

不再进入默认应用：tests、workflow、collaboration、multi-agent。

策略由 `backend/app/api/v1/router_policy.py` 保存为无框架依赖数据，契约测试可以在未安装 FastAPI 时验证生产边界。

## 4. 本轮发现并修复的问题

| 问题 | 风险 | 修复 |
|---|---|---|
| Agent 图在 Graph 和 Service 两处编译 | Checkpointer 行为不一致、运行时错误 | 只由 `create_agent_graph()` 编译一次 |
| HITL 返回 ID 被当成布尔批准 | 高风险工具可能越过确认 | 统一 pending/resume 异步契约 |
| AgentService 使用已删除的同步 HITL 方法 | 确认 API 运行失败 | Service 与 HTTP 端点全部改为 async |
| Transformers 在模块导入时强制加载 | 轻量 API 与规则降级不可用 | 初始化本地模型时再按需导入 |
| LLM 客户端在依赖注入时立即创建 | 测试受宿主代理配置影响 | 首次真实模型调用时延迟创建 |
| 问候分支使用不存在的 `WorkflowType.QA` | 简单请求直接失败 | 改为 `WorkflowType.SIMPLE_QA` |
| 检索节点引用未导入的 settings | 检索静默降级为空上下文 | 统一导入配置对象 |
| 质量门禁信任 LLM 的 overall_score | 文档宣称的权重没有执行 | 对五维分数裁剪后重新加权计算 |
| Agent Monitor 向仓库根目录写跟踪日志 | 测试污染工作区、日志可能泄露路径 | 默认仅控制台；文件日志必须显式指定 |
| Werkzeug/jsonschema 未声明 | 运行时导入失败 | 补入依赖清单 |

## 5. 可复现测试基线

### 5.1 零外部依赖契约

```bash
cd backend
python3 -m unittest discover -s tests/contracts -v
```

结果：`12 passed`（unittest 显示为 `Ran 12 tests ... OK`）。

### 5.2 轻量核心测试

首次建立环境：

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-core.txt
```

运行：

```bash
./scripts/run_core_tests.sh -q
```

2026-08-26 的当前结果：

```text
133 passed, 2 skipped, 12 warnings in 11.06s
```

两个跳过项依赖未安装的模型能力。警告主要来自 Pydantic/FastAPI/SQLAlchemy 旧 API 和旧 Memory 兼容层，已记录但不伪装为已清零。

脚本会禁用宿主机自动注入的 pytest 插件，并固定 `APP_ENV=production`、`DEBUG=false`，因此同时验证生产 Router 暴露边界。

### 5.3 冷启动冒烟验证

使用全新 Compose 数据卷启动 PostgreSQL 16 与 Redis 7 后，生产配置下 Uvicorn 冷启动成功：

```text
Database initialized
Application startup complete
GET /health → 200
OpenAPI paths → 60
retired_exposed → []
```

冷启动过程还发现并修复了 `memories.created_at` 的重复索引声明；该问题此前会让全新 PostgreSQL 在 `Base.metadata.create_all()` 阶段失败。`tests/agent/test_model_metadata.py` 已固定索引名唯一性。

## 6. 当前边界与后续入口

仍未完成：

- Redis/数据库/Milvus 真实集成测试与无 mock 端到端链路；
- 持久化 LangGraph Checkpointer 的跨进程恢复；当前可选实现只是 `MemorySaver`；
- 文档 ACL、检索后 PostgreSQL 存活校验和引用准确率；
- 真实企业写工具、审计记录、拒绝/超时/幂等端到端测试；
- 统一离线评估报告及可复现效果数字。

下一阶段从统一路由指令与结构化输出 Schema 开始，然后落实 ACL、引用和 RAG 离线指标。

## 7. 学习检查点

建议使用以下问题验证是否真正掌握本轮内容：

1. 为什么 Graph 的 `compile()` 必须只有一个所有者？
2. 为什么返回 `request_id` 的异步 HITL 不能写成 `if approved:`？
3. FastAPI 的 `Depends()` 为什么不能只靠 monkeypatch 已注册的依赖函数来隔离测试？
4. 为什么可选模型应该延迟导入，而不是要求所有 API 进程安装 Transformers？
5. 为什么质量评分必须由程序按维度重算，而不能信任模型给出的 `overall_score`？
6. production Router 边界与鉴权分别解决什么问题，为什么二者不能互相替代？
