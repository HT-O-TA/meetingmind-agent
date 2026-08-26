# 阶段 3：RabbitMQ 失败恢复与容量基线

## 1. 本阶段要学会什么

消息进入 RabbitMQ 不等于任务可靠。至少要分别回答：

- 发布者如何知道 broker 已经接管消息？
- 消费者什么时候才能 ACK？
- 处理失败后如何延迟重试，而不是立即热循环？
- 毒消息超过上限后去哪里，任务状态是否同步？
- 同一消息被重复投递时，业务是否会执行两次？
- prefetch、并发和任务超时如何限制资源？

RabbitMQ 官方把 publisher confirm 和 consumer acknowledgement 视为两个相互独立的数据安全机制：前者覆盖发布者到 broker，后者覆盖 broker 到消费者。[Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms) 和 [Reliability Guide](https://www.rabbitmq.com/docs/reliability) 都强调，消费者必须在业务处理完成后才 ACK。

## 2. 原实现的真实问题

阶段盘点发现：

1. Agent Worker 调用了不存在的 `register_consumer`，因此无法启动。
2. 文档 Worker 使用 `message.process()`，异常后的实际行为与“自动回队列”注释不一致，没有有限重试计数。
3. 主队列没有 DLQ，消息 TTL 或队列溢出后的结果不可追踪。
4. 发布没有显式 mandatory 路由保护，channel 也没有形成清晰的 confirm 生命周期。
5. Worker 每次失败会立即重投或丢弃，没有延迟队列、死信状态与错误分类。
6. 向量任务即使部分 chunk 失败仍会标记 completed。
7. 文档任务重试时会重复创建向量/KG 子任务。
8. 所有登录用户都能查询、取消和删除其他用户的任务。
9. Worker 与 Web 没有独立进程入口，Embedding 模型还会在 Worker 导入阶段提前加载。

## 3. 当前可靠投递拓扑

每个业务队列声明三条 durable classic queue：

```text
<queue>          主队列
<queue>.retry    固定 TTL 延迟队列，过期后路由回主队列
<queue>.dead     人工处理的最终死信队列
```

主队列配置 `x-overflow=reject-publish`。队列满时拒绝新消息，让 publisher confirm 暴露失败，避免默认丢弃最老消息。RabbitMQ 对队列长度与 overflow 行为的说明见 [Queue Length Limit](https://www.rabbitmq.com/docs/maxlength)。

正式生命周期：

```text
API 创建任务
→ Redis 写 pending + 用户 + 幂等键
→ persistent message + mandatory publish + publisher confirm
   ├─ confirm：写 published_at
   └─ 未确认：写 publish_failed，可用同一 task_id 安全重发
→ Worker manual delivery，Redis SET NX claim
   ├─ terminal duplicate：直接 ACK，不再执行
   ├─ 成功：业务写入 completed，再 ACK
   ├─ 超时/失败且未超限：confirm 发布到 .retry，再 ACK 原消息
   └─ 超出上限：confirm 发布到 .dead，再 ACK 原消息
```

重试消息或死信消息未获得 publisher confirm 时，原消息只会 `nack(requeue=True)`，不会提前删除。无法解析的坏 JSON 不能获得 task_id，才通过 broker DLX 进入 `.dead`。

DLX 的路由语义见 [Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)。官方同时指出 classic queue 的 broker 内部 DLX 转发不是集群级至少一次保证；因此可解析任务的最终死信在应用层先 confirm 发布到 `.dead`，再 ACK 原消息。

## 4. 幂等、状态和权限

### 4.1 两层幂等

- 创建层：`user_id + task_type + Idempotency-Key` 映射到唯一 task_id，相同请求只发布一次。
- 消费层：`task:claim:<task_id>` 使用 Redis `SET NX`，同一时刻只有一个 Worker 执行；completed/cancelled/dead-letter 等终态的重复消息直接 ACK。

发布结果不确定时不创建新 ID，而是通过 `POST /api/v1/tasks/{task_id}/retry-publish` 重发同一 task_id。即使 broker 曾收到第一次消息，消费者也会把第二份当作终态重复投递跳过。

文档 Worker 创建向量/KG 子任务时，使用 `document_id + chunk_ids hash + kind` 生成稳定幂等键。KG 默认关闭时不再无条件创建 KG 任务。

### 4.2 状态

新增可观察状态：

```text
pending → processing → completed
                   └→ retrying → processing
                               └→ dead_letter
pending → publish_failed → pending（显式重发成功）
任意非终态 → cancelled
```

任务记录还保存 `attempt_count`、`max_attempts`、`error_category` 和 `published_at`。终态不会被迟到 Worker 覆盖。

### 4.3 权限

状态查询、列表、取消、删除、等待和发布重试全部按当前登录用户过滤。未知 task_id 和其他用户的 task_id 对 API 都表现为不可见。

## 5. 并发、超时和进程边界

- `QUEUE_PREFETCH_COUNT` 限制每个消费者未 ACK 的在途消息数；RabbitMQ 对 prefetch 避免消费者过载的说明见 [Consumers](https://www.rabbitmq.com/docs/consumers)。
- `QUEUE_TASK_TIMEOUT` 通过 `asyncio.wait_for` 限制单次处理时间。
- `QUEUE_MAX_RETRIES=2` 表示最多两次额外重试，总尝试数为三次。
- 固定延迟队列避免失败消息立即回到队头形成热循环。
- `python -m app.workers.run` 是独立 Worker 入口；Compose 新增 `worker` 服务，Web 进程只负责发布与查询。
- Embedding 模型改为收到首个向量任务时延迟加载，Worker 注册消费者时不会下载模型。

## 6. 可复现测试

零外部依赖合同测试：

```bash
cd backend
./scripts/run_core_tests.sh -q tests/contracts/test_task_queue_reliability.py
```

覆盖发布失败、创建幂等、用户隔离、并发 claim、成功 ACK、延迟重试、超限死信、重试发布失败、坏消息和任务超时。

真实 Redis + RabbitMQ：

```bash
docker-compose up -d redis rabbitmq
cd backend
REDIS_URL=redis://127.0.0.1:6379/0 \
RABBITMQ_URL=amqp://admin:admin123@127.0.0.1:5672 \
./scripts/run_core_tests.sh -q \
  tests/integration/test_task_queue_redis.py \
  tests/integration/test_rabbitmq_reliability.py
```

真实故障测试会创建唯一临时队列，验证一次延迟重试后进入死信队列，并在结束时只删除自己的临时队列。测试结果为 `2 passed`。

独立 Worker 启动：

```bash
cd backend
PYTHONPATH=. venv/bin/python -m app.workers.run
```

本机已验证文档、向量和 KG 三个消费者能够注册并在 SIGINT 后干净退出。

## 7. 本机轻量容量基线

命令：

```bash
cd backend
APP_ENV=production DEBUG=false \
RABBITMQ_URL=amqp://admin:admin123@127.0.0.1:5672 \
PYTHONPATH=. venv/bin/python scripts/benchmark_queue.py \
  --messages 500 --concurrency 50 --prefetch 50 --payload-bytes 1024 \
  --output evaluation/reports/queue_benchmark_local_20260826.json
```

环境为 RabbitMQ 3.13.7 单节点、本机 loopback、Python 3.12.13。单次实测：

| 指标 | 结果 |
|---|---:|
| 消息数 / 错误 | 500 / 0 |
| 总时长 | 0.140 s |
| 轻量消息吞吐 | 3580.778 msg/s |
| Publisher confirm P95 | 18.619 ms |
| 轻量回调端到端 P95 | 17.746 ms |

原始报告见 [`queue_benchmark_local_20260826.json`](../../backend/evaluation/reports/queue_benchmark_local_20260826.json)。这是消息基础设施的单次本机基线，只执行 1 KiB 消息和轻量回调，不能作为文档解析、Embedding、ASR 或 LLM 的容量数字，也不能直接写进简历当作生产吞吐。

## 8. 当前边界与下一步

- 当前 Compose 是单节点 classic queue，没有 broker 副本高可用。RabbitMQ 官方说明 quorum queue 配合 publisher confirms 和 manual acknowledgements 适合更高数据安全要求，见 [Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)；多节点 quorum 验证留到真实部署环境。
- Redis 状态与 RabbitMQ 发布仍不是同一个原子事务；当前用稳定 task_id、`publish_failed` 和安全重发收敛不确定性，生产级进一步方案是 PostgreSQL transactional outbox。
- 本阶段没有伪造真实文档/音频容量。完整任务容量需要冻结输入文件、模型版本和机器资源后另测。
- Worker 的真实文档 → Embedding → Milvus 闭环仍受本地模型、Milvus 和真实文档数据约束；阶段 4 先接通真实 ASR，再做完整耗时任务基线。

## 9. 学习检查点

1. publisher confirm 和 consumer ACK 分别保护哪一段链路？
2. 为什么重试消息 confirm 之前不能 ACK 原消息？
3. 为什么 `nack(requeue=True)` 不能直接当作重试机制？
4. task_id 幂等与 Redis claim 各解决什么重复问题？
5. 为什么本机 3500+ msg/s 不能代表文档处理吞吐？
6. transactional outbox 能解决 Redis 状态与 broker 发布之间的哪个窗口？
