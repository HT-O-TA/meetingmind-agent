# MeetingMind 离线评估报告

- 生成时间：2026-08-27T11:34:47.205925+00:00
- 数据集：`evaluation/datasets/prompt_injection_synthetic_v1.jsonl`
- 数据类型：`synthetic`
- 样本数：25

> 此报告来自 synthetic 数据，仅验证数据、公式、规则或控制流的可复现回归，不得用于生产效果或简历结论。

## security

| 指标 | 数值 |
|---|---:|
| sample_count | 25 |
| benign_count | 12 |
| malicious_count | 13 |
| false_positive_count | 0 |
| false_positive_rate | 0.0000 |
| false_negative_count | 0 |
| false_negative_rate | 0.0000 |
| expected_action_accuracy | 1.0000 |
| warning_count | 5 |
| synthetic_task_count | 8 |
| synthetic_quarantine_task_completion_rate | 1.0000 |
| all_quarantined_degradation_accuracy | 1.0000 |

## security_by_source

| 分组 | benign_count | expected_action_accuracy | false_negative_count | false_negative_rate | false_positive_count | false_positive_rate | malicious_count | sample_count |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| asr | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 2 | 4 |
| retrieval | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 2 | 4 |
| session | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 2 | 4 |
| tool_result | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 1 | 3 |
| upload | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 1 | 3 |
| user | 2 | 1.0000 | 0 | 0.0000 | 0 | 0.0000 | 5 | 7 |

## 限制

- 全部样本均为 synthetic，只能作为规则与控制流回归，不能外推生产攻击分布。
- synthetic_quarantine_task_completion_rate 使用确定性证据保留代理，不代表真实 LLM 回答质量。
- 规则检测不等于完整安全边界，仍需 ACL、ToolPolicy、HITL、审计和输出校验。
