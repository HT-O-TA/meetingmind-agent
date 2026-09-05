# MeetingMind 统一评估数据卡

## 数据契约

通用数据集每行一个 `evaluation.v1` JSON 对象，可同时包含 `retrieval`、`generation`、`extraction`、`tool`、`route` 和 `system`。缺失分区不会被计入该类指标的分母。

Prompt Injection 数据集使用独立的 `meetingmind.prompt-injection-case.v1`，每条记录包含固定 case_id、来源、标签、测试文本、预期动作，以及可选的安全伴随证据和预期任务状态。它仍由同一个 `scripts/evaluate.py` 执行，不新增线上评测接口。

`sample_kind` 必须明确为：

- `synthetic`：只验证脚本、指标公式和报告格式，不得形成性能结论；
- `deidentified`：项目自编的脱敏/虚构会议样本，只用于检查数据契约和离线指标链路，不代表真实会议效果；
- `real`：来自真实或公开语料的人工标注样本，可用于回归和对外指标；
- 其他值：评估命令默认拒绝，避免误把演示数据当真实结果。

## 划分与防泄漏

- 按会议或文档 ID 分组切分，禁止同一会议的相邻片段跨 Train/Validation/Test。
- Test 标注冻结后只用于最终比较，阈值选择只使用 Validation。
- 问题、相关文档、抽取标签和工具期望均需要双人复核或保留复核状态。
- 所有会议文本在入库前脱敏；数据版本用文件哈希和 Git 提交共同标识。

## 指标解释

- Retrieval：Recall@K、MRR、二元相关性 nDCG@K。
- Generation：当前离线无评判模型模式仅提供词面 Faithfulness/Answer Relevancy 代理；报告会显式带 `_lexical_proxy`，不得称为 RAGAS 分数。
- Extraction：字段级 Precision、Recall、F1（报告同时提供 `todo_f1` 别名）和原始 JSON 合法率。
- Tool：工具选择、参数字段 F1、成功率、HITL 触发准确率。
- System：平均/P95 时延、顺序执行吞吐代理、错误率、Token 和成本。
- Prompt Injection：FPR、FNR、预期动作准确率、合成隔离后任务完成率和全隔离正确降级率；按 user、session、upload、retrieval、tool_result 和 asr 分来源报告。

## 当前文件

`datasets/sample_eval.jsonl` 是 3 条通用合成样例，只用于测试评估代码。

`datasets/meetingmind_deidentified_v1.jsonl` 是当前 8 条项目自编脱敏会议样例，覆盖检索、引用和待办抽取。它可作为回归基线，但不是公开语料，也不能替代真实长会议评测。对应报告保存在 `reports/meetingmind_deidentified_v1.{json,md}`。

`datasets/meetingmind_real_v1_sources.jsonl` 是从 AliMeeting Eval TextGrid 整理出的 8 个会议源记录；`datasets/meetingmind_real_v1_candidates.jsonl` 是从 VCSUM `long_test` 整理出的 26 场会议、158 条问题/答案/引用候选（26 条整体结论、132 条主题问答），并附带 130 条 VCSUM 和 64 条 AliMeeting 待办候选及 228 条约束候选。`datasets/meetingmind_real_v1_ai_reviews.jsonl` 覆盖全部 580 个审核单元，状态保持为 `ai_reviewed_silver`。正式冻结评测文件是 `meetingmind_real_v1_evaluation.jsonl`：100 条任务、28 场会议、全部由 `reviewer=ht` 人工审核，当前仍明确标记 `gold=false`，不能称为 gold 数据集。

`datasets/prompt_injection_synthetic_v1.jsonl` 是冻结的 25 条合成安全回归集，包含 12 条正常/易误判样本、5 条直接注入和 8 条间接注入。`prompt_injection_synthetic_thresholds.json` 只用于防止已知样本回归；它不是生产阈值。对应报告中的 0 FPR、0 FNR 和 1.0 合成任务完成率只描述该固定数据集。

真实会议 Prompt Injection 数据与真实模型端到端任务完成率尚未形成可核验评估文件，因此不得把合成报告数字用于简历或生产安全结论。

线上性能请使用仓库根目录 `scripts/measure_agent_runtime.py`，它只记录真实 API 返回的时延、失败率和预算账本。没有服务、模型用量或单价时，成本字段会保持为空，不会把预算上限冒充实际成本。
