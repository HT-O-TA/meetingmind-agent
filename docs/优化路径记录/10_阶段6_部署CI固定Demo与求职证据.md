# 阶段 6：部署、CI、固定 Demo 与求职证据

## 1. 本阶段结论

阶段 6 已完成可由当前机器独立验证的部分：轻量 Web/Worker 与模型能力解耦、开发 Compose、生产配置失败关闭、前后端镜像、CI 门禁、三组固定 Demo、可核验指标索引和简历描述边界。

这不是“生产环境已经上线”。本机没有验证 TLS、备份恢复、多节点 PostgreSQL/Redis/RabbitMQ、Milvus 容量、外部 Secret Manager 或真实流量；`docker-compose.prod.yml` 只是带安全前置条件的生产参考覆盖层。

| 项目 | 结果 | 证据 |
|---|---|---|
| 开发部署预检 | 通过 | `scripts/preflight_deploy.py` |
| 缺少生产密钥 | 按预期拒绝启动 | 5 个必填变量检查 + Compose 必填插值 |
| 后端/前端镜像 | Docker CLI 显示 448 MB / 50 MB | 本机 Docker 29.1.3 |
| 后端运行时依赖 | `pip check` 通过 | `backend/requirements-runtime.lock` |
| 容器联动 | 默认 6 服务运行；后端、前端、API 代理均 HTTP 200 | Worker 注册 3 个消费者，253099 byte 数据集经 Nginx 代理返回 |
| 核心测试 | 175 passed，2 skipped | `backend/scripts/run_core_tests.sh` |
| 真实基础设施集成 | 4 passed | PostgreSQL、Redis、RabbitMQ |
| 前端 | 44 passed，生产构建通过 | Vitest + Vite |
| 中危/高危静态扫描 | 0 | MD5 键、MCP 监听边界和 SQL 参数绑定已收敛 |
| 固定 Demo | 3/3 通过 | 队列恢复、ASR 证据、LoRA 抽取 |

汇总原始值见 `backend/evaluation/reports/stage6_delivery_local_20260826.json`。

## 2. 部署边界

默认 Compose 只启动可复现的轻量核心：

```text
Browser → Nginx/Vue → FastAPI Web
                         ├→ PostgreSQL
                         ├→ Redis
                         └→ RabbitMQ → lightweight Worker

可选 profile: Neo4j / Prometheus / Grafana
独立能力: FunASR GPU Worker / Embedding-Reranker / LoRA inference / Milvus
```

Web 镜像不包含 Torch、FunASR、Transformers、训练权重或模型缓存。这样可以分别回答“业务 API 是否可部署”和“GPU 模型服务需要哪些资源”，也避免改一个前端接口就重建数 GB 模型镜像。

后端构建上下文从首次误带本地环境的 263.7 MB 收敛到 2.789 MB。完整运行时依赖冻结在 `requirements-runtime.lock`；`requirements-runtime.txt` 仍是便于理解和升级的直接依赖清单。两者变化后必须共同重建并执行容器冒烟。

## 3. 开发环境一键复现

```bash
cd /home/lenovo/A/meetingmind-agent
cp .env.example .env
python3 scripts/preflight_deploy.py --mode development
docker-compose up -d --build
docker-compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8080/
```

停止服务但保留数据：

```bash
docker-compose down
```

可选观测与图谱组件：

```bash
docker-compose --profile observability up -d
docker-compose --profile knowledge-graph up -d neo4j
```

这组命令证明核心服务可启动。若要调用 LLM，需要在私有 `.env` 中配置 `LLM_API_KEY`；若要运行 Dense 模型、Milvus 或 ASR，应按对应阶段文档启动独立能力，不能把默认 Compose 描述成完整 AI 生产栈。

## 4. 生产配置为何必须先失败

生产参考覆盖层要求显式提供：

- `POSTGRES_PASSWORD`；
- `RABBITMQ_USER` 与 `RABBITMQ_PASSWORD`；
- 至少 32 字符、非示例值的 `SECRET_KEY`；
- 不含通配符或 localhost 的 `CORS_ORIGINS`。

检查命令：

```bash
python3 scripts/preflight_deploy.py --mode production --env-file /path/to/production.env
docker-compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

预检报告只写“是否存在”，不写密钥值。应用本身也会在 production 拒绝短密钥、示例密钥、`DEBUG=true` 和通配 CORS。`SecretProvider` 默认从进程环境读取，并允许以后注入 Vault/KMS 适配；目前只有 Jira Token 接入该边界，不能声称已经联通 Vault。

## 5. CI 门禁

每次 push/PR 执行：

1. Python 3.11 与 3.12 的正式轻量核心测试；
2. 合成微调数据重新生成并检查 Git diff，防止数据漂移；
3. Python 源码编译检查；
4. 前端 `npm ci`、44 个测试和生产构建；
5. PostgreSQL/Redis/RabbitMQ 下的 ACL、审计幂等、任务幂等、重试/DLQ 集成测试；
6. Bandit 中危/高危扫描与开发 Compose 预检；
7. 前后端镜像构建。

镜像发布只在 `v*` Tag 或手工触发时执行，使用 `GITHUB_TOKEN` 发布到 GHCR；普通 main push 不发布可变镜像，也不依赖个人 Docker Hub 密钥。

## 6. 三个固定 Demo

### 6.1 准备

```bash
docker-compose up -d postgres redis rabbitmq

cd backend
python -m venv .venv-asr
source .venv-asr/bin/activate
pip install -r requirements-core.txt
# 按本机 CUDA 安装 PyTorch 后：
pip install -r requirements-asr.txt
deactivate
```

LoRA Demo 还要求阶段 5 的本地 Qwen3-0.6B 与 LoRA adapter；这些大文件由 Git 忽略。

统一运行：

```bash
cd /home/lenovo/A/meetingmind-agent
backend/venv/bin/python scripts/run_fixed_demos.py
```

也可以单独运行：

```bash
backend/venv/bin/python scripts/run_fixed_demos.py --demo queue
backend/venv/bin/python scripts/run_fixed_demos.py --demo asr
backend/venv/bin/python scripts/run_fixed_demos.py --demo lora
```

输出默认进入被 Git 忽略的 `artifacts/fixed-demos/`，避免把临时 ID 和重复运行结果混入正式报告。

### 6.2 Demo A：RabbitMQ 失败恢复

录制顺序控制在 90 秒：

1. 先画出 main → retry → main → dead；解释 confirm 与 ACK 保护不同链路。
2. 运行 `--demo queue`。
3. 指出实测 `attempt_count=2`、延迟重试 1 次、确认死信 1 次。
4. 指出拓扑在 finally 删除；故障是确定性注入，不是生产成功率。

### 6.3 Demo B：WAV 到持久证据

录制顺序控制在 2 分钟：

1. 展示固定公开 WAV 与 `audio_transcribe` 队列。
2. 运行 `--demo asr`，观察模型懒加载和任务完成。
3. 展示 `meetingmind.asr-evidence.v1`、正文、时间戳、匿名说话人和“需人工核验”纪要。
4. 明确这是一条公开单句烟测，不是会议 CER/DER；临时数据库记录会自动删除。

### 6.4 Demo C：LoRA 严格抽取

录制顺序控制在 90 秒：

1. 展示固定输入：“请成员丙在周五前整理发布核对表”。
2. 运行 `--demo lora`。
3. 展示负责人、期限、来源、说话人、时间戳及 `schema_valid=true`。
4. 回到四组对比报告，解释合成集 LoRA 业务字段 F1=0.919，但双待办仍会漏项，不能外推真实会议。

代码与脚本已完成；真正的视频文件仍需用户用录屏软件完成，因为录制需要人工口述、窗口选择和隐私检查。

## 7. 简历证据索引

| 可讲述内容 | 代码 | 测试/命令 | 报告 | 不能扩大的说法 |
|---|---|---|---|---|
| RAG ACL、引用、融合与统一评估 | `app/services/rag_service.py`、`vector_search_service.py` | 核心测试 + PostgreSQL ACL | 阶段 1 文档 | 没有真实数据效果数字 |
| Agent 安全写工具 | ToolPolicy、HITL、ToolExecutor、JiraClient | 工具合同 + PG 审计/幂等 | 阶段 2 文档 | 未完成真实 Jira 站点写入 |
| RabbitMQ 失败恢复 | `app/core/rabbitmq.py`、Worker | 固定 Demo + 集成测试 | 阶段 3/6 报告 | 单机吞吐不等于业务吞吐 |
| FunASR 音频证据 | `asr_service.py`、`audio_worker.py` | 公开评测 + 队列 Demo | 阶段 4 报告 | 不报告会议 CER/DER |
| LoRA/QLoRA 实验 | `backend/finetuning` | 四组固定测试 + Demo | 阶段 5 报告 | 全部是合成数据 |
| 可复现交付 | Compose、Dockerfile、CI、preflight | 镜像/容器/安全扫描 | 阶段 6 报告 | 不声称生产已上线 |

可直接用于简历、同时保持真实性的表述示例：

> 收敛企业会议智能应用的 RAG/Agent 主链路，完成文档 ACL、引用溯源、ToolPolicy/HITL/幂等审计与 RabbitMQ 重试/DLQ；以 175 项轻量测试和 4 项真实基础设施集成测试建立回归门禁。

> 基于 FunASR 构建 WAV→RabbitMQ→PostgreSQL 的时间戳/匿名说话人证据链路，并用 Qwen3-0.6B 完成 LoRA/QLoRA 同协议实验；LoRA 在 16 条项目自编合成测试集上的业务字段 F1 为 0.919，明确不外推真实会议质量。

> 将 Web/Worker 与 GPU 模型能力解耦，构建 448 MiB 后端与 50 MiB 前端镜像、生产密钥失败关闭和 GitHub Actions 多层门禁；开发 Compose 已在本机完成容器联动验证。

## 8. 学习检查点

1. 为什么“容器能 build”和“应用能 import/startup/health”是三层不同证据？
2. 为什么模型不进入 Web 镜像，代价是什么？
3. lock 文件解决了什么，又为什么仍不能替代镜像 digest 与 SBOM？
4. 为什么生产 preflight 的正确结果可以是失败？
5. GitHub Actions 为什么要把无外部依赖测试和真实基础设施测试拆开？
6. 为什么固定 Demo 输入比每次随意演示更适合求职证据？
7. 简历数字如何绑定数据种类、样本数、代码和报告？

## 9. 尚需用户或外部环境完成

- 人工录制三段视频，并检查屏幕中不出现 Token、邮箱或其他隐私；
- 提供 Jira Cloud 凭据与测试项目权限，完成一次真实高风险写入、HITL 和回查；
- 提供合法、脱敏、带真值的会议/RAG 数据，才能报告真实 RAG、CER、DER 和抽取指标；
- 在目标生产环境完成 TLS、域名、备份恢复、Secret Manager、多节点高可用、镜像漏洞/SBOM 与容量验收；
- 前端主包仍约 1.235 MB，生产构建通过但有 chunk size 告警，后续可通过 Element Plus 按需导入继续优化。
