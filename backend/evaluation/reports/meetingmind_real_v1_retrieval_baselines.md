# MeetingMind 本地检索收官基线

## 实验范围

- 数据：`meetingmind_real_v1_evaluation.jsonl`
- QA 任务：40 条
- 评测 QA 覆盖会议：20 场（冻结总集仍为 28 场；本报告只含 40 条 QA）
- 检索范围：已知 `meeting_id` 后的会议内排序，不是全库检索
- 去重：按规范化文本去重；报告记录了被合并的重复文档数量
- 方案：字符 n-gram 关键词、BGE-M3 Dense、关键词 + Dense、关键词 + Dense + BGE-Reranker
- 模型：全部本地模型，不访问模型源

## 总体结果

| 方案 | Recall@5 | Precision@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|
| BM25/关键词 | 0.0563 | 0.1950 | **0.4326** | **0.2133** |
| Dense | 0.0622 | 0.1650 | 0.3919 | 0.1861 |
| Hybrid | **0.0732** | **0.2000** | 0.3958 | 0.2080 |
| Hybrid + Reranker | 0.0521 | 0.1750 | 0.3706 | 0.1899 |

## 会议级 Bootstrap 结果

Bootstrap 以会议为单位重采样，而不是把 40 条任务当作 40 个独立样本。完整区间见：
`meetingmind_real_v1_retrieval_cluster_bootstrap.json`。

- BM25 Recall@5：0.0554，95% 区间 0.0281—0.0875
- Dense Recall@5：0.0622，95% 区间 0.0365—0.0872
- Hybrid Recall@5：0.0734，95% 区间 0.0434—0.0996
- Hybrid + Reranker Recall@5：0.0522，95% 区间 0.0268—0.0785

## 结论和限制

1. 在本次去重后的会议内排序实验中，Hybrid 的 Recall@5 最高；Reranker 没有超过 Hybrid，不能宣称 Reranker 整体领先。
2. 这是已知会议内的受控排序实验，不代表跨所有会议的全库检索能力；全库实验应另设评测口径。
3. 当前 QA 的一个问题对应很多相关片段，因此 Recall@5 会被严格压低；同时应补充 Hit@5、答案级引用覆盖率和人工引用充分性复核。
4. 这是真实会议离线检索结果，不等于完整端到端问答质量。
