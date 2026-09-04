# MeetingMind 离线评估报告

- 生成时间：2026-09-04T08:41:50.635079+00:00
- 数据集：`backend\evaluation\datasets\meetingmind_deidentified_v1.jsonl`
- 数据类型：`deidentified`
- 样本数：8
- Top-K：5

> 此报告来自脱敏/项目自编会议样本，可用于工程回归；在样本量扩大并完成独立复核前，不作为生产泛化结论。

## retrieval

| 指标 | 数值 |
|---|---:|
| mrr | 0.7292 |
| ndcg_at_k | 0.7891 |
| recall_at_k | 1.0000 |

## generation

| 指标 | 数值 |
|---|---:|
| answer_relevancy_lexical_proxy | 0.1750 |
| citation_accuracy | 1.0000 |
| faithfulness_lexical_proxy | 0.5564 |

## extraction

| 指标 | 数值 |
|---|---:|
| f1 | 0.6458 |
| json_valid_rate | 1.0000 |
| precision | 0.6875 |
| recall | 0.6250 |
| todo_f1 | 0.6458 |
