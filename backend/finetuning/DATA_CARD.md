# Meeting Todo Synthetic v1 数据卡

## 基本信息

| 字段 | 值 |
|---|---|
| 数据文件 | `data/meeting_todo_synthetic_v1.jsonl` |
| Schema | `meetingmind.todo-extraction.v1` |
| 总样本 | 76 |
| Train / Validation / Test | 48 / 12 / 16 |
| 含待办样本 | 36 / 8 / 12 |
| 真实用户记录 | 0 |
| 人工复核记录 | 0 |
| 生成器 | `build_dataset.py` |

数据集是项目自编的中文合成会议片段。它没有使用用户日志，也没有把现有 AliMeeting 转写自动伪装成待办真值。每条记录都显式标记：

- `source_kind=project_authored_synthetic`；
- `annotation_method=deterministic_template_ground_truth`；
- `contains_real_user_data=false`；
- `human_reviewed=false`。

## 任务与字段

输入包含 `source_id`、`source_type` 和带匿名说话人/时间戳的会议片段。输出是待办 JSON 数组，每项必须包含：

```text
content, assignee, deadline, priority,
source_id, source_type, speaker, timestamp,
uncertainties, degradation_info
```

该字段集与线上 `TodoOutput` 兼容，但评估层更严格：缺字段、额外字段、错误枚举和错误类型都会判为 Schema 失败。负责人或期限未知时使用空字符串，并在 `uncertainties` 中保留原因。

## 构造与切分

正例覆盖明确分配、个人承诺、缺负责人、缺期限、高优先级和同一片段双待办；负例覆盖建议、疑问、已完成、已取消、暂缓以及只有讨论而没有任务的场景。

每个样本使用独立 `meeting_id`，Train、Validation、Test 按会议完全隔离。内容词组在不同切分间不重复，但语言模板有共享，因此这只能检查受控模板泛化，不能代表开放域会议泛化。

## 隐私与质量检查

`build_dataset.py` 每次生成时都会检查：

- sample_id 唯一；
- meeting_id 无跨切分泄漏；
- 邮箱、中国大陆手机号和身份证号模式；
- 真值 JSON 的字段、类型和枚举；
- `content`、`assignee`、`deadline` 必须能在原片段找到；
- `source_id` 与 `source_type` 必须回指输入。

这里的“脱敏”准确含义是“从源头只使用匿名合成角色”，不是已经证明能处理任意真实 PII 的脱敏系统。

## 适用范围

可以用于：

- 学习 SFT、LoRA、QLoRA、assistant-only loss masking；
- 验证数据构建、固定切分、Schema 校验和评测报告；
- 检查 Prompt-only、Few-shot、适配器协议是否使用同一测试集。

不可以用于：

- 宣称真实会议待办抽取准确率；
- 宣称真实姓名、组织和日期表达的泛化能力；
- 替代真实会议的双人标注、一致性检查和错误分析；
- 自动创建正式业务待办。

## 来源与再分发

文本由本项目确定性生成，不含 AliMeeting 原文。仓库当前没有根级许可证，因此不要把本数据集脱离项目单独再授权或声称为公共领域数据。

官方 AliMeeting4MUG Action Item Detection 数据可作为下一轮真实公开真值来源，但官方基线下载流程要求 ModelScope 个人 Token；当前未获得完整数据及对应使用条件，所以本轮没有下载、转换或混入它。

## 已知局限

1. 76 条规模很小，且测试集只有 16 条。
2. 标签由模板确定，未经人工复核。
3. 训练和测试共享语言模板，易高估适配器效果。
4. 每个样本只有一个短片段，缺少长会议、跨轮指代和隐式承诺。
5. 只有两条双待办测试样本，不能充分测量多项召回。
