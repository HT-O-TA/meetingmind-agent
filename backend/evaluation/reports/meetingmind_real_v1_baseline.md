# MeetingMind 真实会议 100 条离线基线

- 数据集：`backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl`
- 数据集哈希：`8b82b681b130084b3eacdb9a18371319c419dfd695f2345132bce2d6928a9e35`
- 样本数：100

> 这是候选结果对照复核标签的离线基线，不是端到端线上性能结论。

## retrieval

- mrr：1.0
- ndcg_at_k：1.0
- recall_at_k：0.37025592688760445

## generation

- citation_accuracy：1.0

## extraction_by_unit_type

- todo：{"f1": 0.09444444444444444, "precision": 0.1111111111111111, "recall": 0.7537037037037037}
- constraint：{"f1": 0.5833333333333334, "precision": 0.5833333333333334, "recall": 0.95}

## todo

- todo_f1：0.09444444444444444
- precision：0.1111111111111111
- recall：0.7537037037037037

## 系统性能

- P50/P95 延迟：未测量
- 失败率：未测量
- 单请求成本：未测量

## 限制

- 质量基线比较的是已生成候选与复核标签，不是模型重新推理结果。
- 当前冻结集只有 100 条，覆盖 28 场会议；100 条均已由 reviewer=ht 完成人工审核。
- 未连接真实模型、数据库或队列，因此不报告端到端延迟、失败率和成本。
