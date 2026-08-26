# 阶段 2：Agent 安全工具闭环

## 1. 本阶段要学会什么

Agent 的价值不在于“会选工具”，而在于能把不稳定的模型输出收敛为受控业务动作。本阶段把正式执行顺序固定为：

```text
ToolCall 外层 Pydantic Schema
→ 具体工具参数 Schema
→ ToolPolicy（工作流、风险、重试边界）
→ 绑定当前用户和单次调用的 HITL
→ ToolExecutor
→ PostgreSQL 持久审计与幂等门禁
```

必须区分三个概念：

- 参数合法不代表操作被允许；Schema 只回答“输入长什么样”。
- 用户说“创建”不代表可以绕过确认；外部副作用和不可撤销性决定风险。
- HTTP 超时不代表创建失败；非幂等 POST 的上游结果可能未知，自动重放可能创建两个 Issue。

## 2. 本次真实性收敛

原企业工具会返回 `PROJ-123`、`doc_abc123` 等固定假 ID。现在正式注册表只允许一个已实现目标：Jira Cloud REST API v3；飞书、Notion 和邮件 mock 不再注册，也不再被 ToolExecutor 宣称为支持能力。

Jira 客户端的边界如下：

- 创建：`POST /rest/api/3/issue`，描述使用 Atlassian Document Format；
- 查询：`GET /rest/api/3/issue/{issueKey}`；
- 更新字段：`PUT /rest/api/3/issue/{issueKey}`；
- 401、403、404、409、429、5xx、网络和超时有稳定错误分类；
- GET/PUT 可在 429/5xx 上有界重试并尊重 `Retry-After`；
- 创建是非幂等写，客户端和 ToolPolicy 都只允许一次请求，不在超时/网络错误后自动重放；
- 配置缺失、URL 不是 HTTPS 或持久审计不可用时，外部写关闭执行，绝不回退为 mock 成功。

官方依据：Jira Cloud 的创建接口、201 响应和权限要求见 [Jira Cloud REST API v3 - Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)；个人脚本可使用账号邮箱与 API Token 的 Basic Auth，应用集成优先 OAuth 2.0，见 [Basic auth for REST APIs](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/) 和 [Security overview](https://developer.atlassian.com/cloud/jira/platform/security-overview/)；429、`Retry-After` 与仅重试幂等请求的原则见 [Jira Cloud rate limiting](https://developer.atlassian.com/cloud/jira/platform/rate-limiting/)。

## 3. HITL 为什么要绑定“用户 + 单个调用”

只保存全局 `confirmation_status=approved` 会产生两个问题：

1. 用户 A 可能读取或批准用户 B 的确认请求；
2. 一次批准可能让同一计划中的多个高风险工具全部放行。

现在确认详情保存 `user_id` 和当前工具调用的 `idempotency_key`。确认查询、响应和恢复 API 均要求登录，并只返回当前用户拥有的请求。恢复时只批准匹配该幂等键的一次调用；后续高风险调用必须产生新的确认。

## 4. 审计和幂等状态机

`tool_execution_audits` 保存：用户、线程、Agent run、工具、风险、操作类型、确认状态、参数摘要、请求哈希、幂等键、状态、外部 ID 和错误分类。Token、密码、Secret 等字段在落库前递归脱敏。

```text
不存在幂等键记录 → started → succeeded / failed / unknown
相同键 + 相同参数 + succeeded → replay 已保存结果，不调用上游
相同键 + 不同参数 → blocked（键冲突）
相同键 + started/failed/unknown → blocked（需要人工核对）
```

对非幂等外部写，超时、网络错误或不确定的上游错误记为 `unknown`。这时正确动作是到 Jira 查询是否已创建，再由人决定新开一次 Agent run，而不是盲目重试。

## 5. 可复现验证

零外部依赖合同测试：

```bash
cd backend
./scripts/run_core_tests.sh -q \
  tests/unit/test_jira_client.py \
  tests/contracts/test_stage2_tool_safety.py
```

真实 PostgreSQL 审计与幂等测试：

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://postgres:password@127.0.0.1:5432/meetingmind' \
  ./scripts/run_core_tests.sh -q tests/integration/test_tool_audit_postgres.py
```

已有数据库显式建表：

```bash
cd ..
DATABASE_URL='postgresql+asyncpg://postgres:password@127.0.0.1:5432/meetingmind' \
  PYTHONPATH=backend backend/venv/bin/python \
  backend/app/db/migrations/0007_add_tool_execution_audits.py
```

## 6. 真实 Jira 联调（需要项目所有者完成）

将 `backend/.env.example` 复制为 `backend/.env`，填写 Jira 站点、账号邮箱和 API Token。Token 只能放本机 `.env`，不能提交 Git。先执行只读请求：

```bash
cd backend
PYTHONPATH=. venv/bin/python scripts/smoke_jira.py --issue-key MM-1
```

确认账号具备目标项目的 Create issues 权限后，再执行受双重参数保护的写入：

```bash
PYTHONPATH=. venv/bin/python scripts/smoke_jira.py \
  --create-project MM \
  --summary 'MeetingMind 真实工具联调' \
  --confirm-create CREATE
```

本机当前没有 Jira 站点、账号、Token 和项目 Key，因此只完成了 MockTransport 合同验证，不能宣称“真实 Jira 联调成功”。真实联调后应保存返回的 Issue Key、对应审计行和演示截图，但不要保存 Token。

## 7. 学习检查点

完成真实联调前，应该能独立回答：

1. 为什么参数 Schema、授权策略和 HITL 不能合并成一个布尔判断？
2. 为什么 Jira 创建超时后不能直接重试？
3. 幂等键冲突与结果回放分别意味着什么？
4. 为什么审计写入失败时外部写要 fail closed？
5. 如何从 401、403、429 和 timeout 判断下一步排查方向？

## 8. 当前验收结论

- 已完成：唯一真实 Jira 适配器、错误分类、重试边界、参数验证、ToolPolicy/HITL 顺序、用户隔离、单调用批准、PostgreSQL 审计、幂等回放与冲突测试。
- 已验证：Jira 合同与安全测试 12 项通过；真实 PostgreSQL 审计事务测试 1 项通过。
- 外部阻塞：缺少 Jira 真实凭据与项目权限，所以完整“会议待办 → 真实 Issue → 外部 ID”演示尚未关闭。
- 明确移出主线：飞书、Notion、Email mock；MCP 框架仍默认关闭，不等同于真实 Server 联调。
