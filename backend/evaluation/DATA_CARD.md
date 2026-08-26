# MeetingMind 统一评估数据卡

## 数据契约

每行一个 `evaluation.v1` JSON 对象，可同时包含 `retrieval`、`generation`、`extraction`、`tool`、`route` 和 `system`。缺失分区不会被计入该类指标的分母。

`sample_kind` 必须明确为：

- `synthetic`：只验证脚本、指标公式和报告格式，不得形成性能结论；
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
- Extraction：字段级 Precision、Recall、F1 和原始 JSON 合法率。
- Tool：工具选择、参数字段 F1、成功率、HITL 触发准确率。
- System：平均/P95 时延、顺序执行吞吐代理、错误率、Token 和成本。

## 当前文件

`datasets/sample_eval.jsonl` 是 3 条合成样例，只用于测试评估代码。真实 AliMeeting 数据与真实服务预测尚未在当前工作区形成可核验、冻结的评估文件，因此不得引用样例报告数字。
