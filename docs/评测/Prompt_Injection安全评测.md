# Prompt Injection 安全评测

定位：离线验证输入预处理层的直接注入拒绝、间接注入隔离和安全证据保留能力。它是跨版本验收机制，不是六链路中的运行时层，也不属于反思校验层。

当前状态：`prompt-injection-synthetic.v1` 合成基线、自动化指标、跨层契约测试和 CI 门禁已经完成；真实会议分布和真实模型效果仍待后续数据验证。

## 1. 评测对象与边界

运行时输入层负责检测、标记、隔离或拒绝；本评测只负责准备固定样本、执行回归、计算指标和保存报告，不参与线上请求决策。

样本至少覆盖：

1. 用户问题中的直接注入。
2. 会话历史、上传文档、RAG 片段、工具结果和 ASR 转写中的间接注入。
3. 容易误判的正常内容，例如会议中引用恶意话术、安全研究讨论、角色扮演、代码片段和包含“忽略前文”等字样的普通记录。
4. 隔离恶意片段后仍有足够安全证据完成任务，以及全部证据被隔离后必须明确降级的场景。

本评测不验证 ACL、工具参数 Schema、HITL、幂等和输出事实性；这些能力在各自链路单独验收。

## 2. 固定 Bad Case 数据集

每条样本至少记录：

| 字段 | 含义 |
|---|---|
| case_id、dataset_version | 稳定编号和数据集版本 |
| source | user、session、upload、retrieval、tool_result 或 asr |
| text/content_ref | 测试文本或可复现的受控引用 |
| label | benign、direct_injection 或 indirect_injection |
| expected_action | allow、quarantine 或 reject |
| task | 隔离前后需要完成的业务任务 |
| expected_evidence/output | 应保留的安全证据或最小正确结果 |

当前冻结文件为 `backend/evaluation/datasets/prompt_injection_synthetic_v1.jsonl`，共 25 条：12 条正常/易误判样本、5 条直接注入和 8 条间接注入，覆盖 user、session、upload、retrieval、tool_result 与 asr。新增或修改样本必须产生新 dataset_version，不能静默修改旧标签。样本只使用合成或脱敏内容，不保存真实账号、凭据和个人敏感信息。

## 3. 核心指标

| 指标 | 口径 | 合成 v1 结果 |
|---|---|---:|
| 误报率 FPR | 正常样本被错误隔离或拒绝的数量 / 正常样本总数 | 0/12 |
| 漏报率 FNR | 注入样本被错误放行的数量 / 注入样本总数 | 0/13 |
| 预期动作准确率 | allow/quarantine/reject 与标签一致的样本数 / 全部样本 | 25/25 |
| 合成隔离后任务完成率 | 确定性证据代理仍保留所需安全事实的可继续任务数 / 可继续任务总数 | 7/7 |
| 全隔离正确降级率 | 已无安全证据时返回明确失败或降级的任务数 / 全隔离场景总数 | 1/1 |

FPR 和 FNR 按 source 分别报告，避免总平均数掩盖某一入口的缺陷。合成集已经设置零回归阈值，但这只表示后续修改不能破坏 25 条已知样本；生产阈值必须在真实或公开人工标注数据上依据业务风险重新确定。

## 4. 执行与报告

统一执行命令：

```bash
cd backend
python3 scripts/evaluate.py --allow-synthetic \
  --dataset evaluation/datasets/prompt_injection_synthetic_v1.jsonl \
  --thresholds evaluation/prompt_injection_synthetic_thresholds.json \
  --enforce-thresholds \
  --output evaluation/reports/prompt_injection_synthetic_v1.json
```

每次调整注入规则、信任分区或隔离逻辑时：

1. 对固定版本数据集执行确定性规则，生成按来源拆分的混淆矩阵。
2. 对隔离场景继续运行对应业务任务，检查保留证据、citations 和最终状态。
3. 与上一规则版本比较 FPR、FNR、任务完成率和退化样本。
4. 保存规则版本、数据集哈希、运行环境、失败样本编号和指标；报告不复制测试正文。

`backend/tests/contracts/test_prompt_injection_evaluation_contract.py` 让同一数据集驱动规则指标、会话记忆再输入隔离、规划上下文、检索 citations、工具结果隔离与 ASR 索引测试；GitHub Actions 再执行统一评估命令并强制合成阈值。当前报告位于 `backend/evaluation/reports/prompt_injection_synthetic_v1.json` 和同名 Markdown 文件。

即使当前合成集全部通过，也只能说明“25 条冻结合成样本未回归”，不能宣称系统能够防住所有 Prompt Injection。合成隔离后任务完成率使用确定性证据保留代理，不等于真实 LLM 回答质量。

## 5. 与六链路的关系

- 输入预处理层：拥有线上检测、信任标记、拒绝与隔离逻辑，是本评测的主要被测对象。
- 规划推理层和工具层：消费隔离后的上下文，并不得恢复或执行已隔离内容。
- 反思校验层：检查当前任务是否仍满足完成条件，但不负责构造本评测数据集或统计安全分类指标。
- 输出层：在无安全证据时如实呈现 partial、failed 或 rejected，不伪装成功。
