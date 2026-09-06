# MeetingMind 离线评估报告

- 生成时间：2026-09-04T15:47:25.750806+00:00
- 数据集：`backend\evaluation\datasets\sample_eval.jsonl`
- 数据类型：`synthetic`
- 样本数：3
- Top-K：5

> 此报告来自 synthetic 数据，仅验证数据、公式、规则或控制流的可复现回归，不得用于生产效果或简历结论。

## retrieval

| 指标 | 数值 |
|---|---:|
| mrr | 0.5000 |
| ndcg_at_k | 0.5169 |
| recall_at_k | 0.6667 |

## generation

| 指标 | 数值 |
|---|---:|
| answer_relevancy_lexical_proxy | 0.1601 |
| citation_accuracy | 0.6667 |
| faithfulness_lexical_proxy | 0.5000 |

## extraction

| 指标 | 数值 |
|---|---:|
| f1 | 0.8333 |
| json_valid_rate | 1.0000 |
| precision | 0.8333 |
| recall | 0.8333 |
| todo_f1 | 0.8333 |

## tool

| 指标 | 数值 |
|---|---:|
| hitl_trigger_accuracy | 1.0000 |
| parameter_accuracy | 0.8889 |
| selection_accuracy | 0.6667 |
| success_rate | 0.6667 |

## route

| 指标 | 数值 |
|---|---:|
| complexity_accuracy | 0.6667 |
| fallback_rate | 0.3333 |
| task_accuracy | 1.0000 |

## system

| 指标 | 数值 |
|---|---:|
| mean_latency_ms | 156.6667 |
| p50_latency_ms | 120.0000 |
| p95_latency_ms | 260.0000 |
| sequential_throughput_proxy_rps | 6.3830 |
| error_rate | 0.3333 |
| total_tokens | 260 |
| total_cost | 0.0045 |

## route_threshold_recommendation

| 指标 | 数值 |
|---|---:|
| threshold | 0.0000 |
| f1 | 1.0000 |
| coverage | 1.0000 |
| status | recommendation_only_not_applied |
