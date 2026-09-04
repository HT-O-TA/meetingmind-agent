# 本地会议数据审查记录

本目录用于本机真实/公开会议评测，不把原始音频和数据仓库提交到 Git。

## 当前数据

### `Eval_Ali`

- 数据集：AliMeeting Eval（阿里多方会议语料）；
- 本地内容：8 个远场 8 通道 WAV、25 个近场单通道 WAV、33 个 TextGrid；
- 实际统计：8 个会议会话；远场 8 通道音频合计约 4.3 小时，近场文件是按说话人拆开的同一批会话；单场约 25.9～37.3 分钟；
- TextGrid：包含说话人 tier、起止时间和人工转写文本；
- 适合验证：ASR、说话人区分、时间戳、多人会议切分和下游 RAG 输入；
- 来源与许可：OpenSLR SLR119，页面标注 CC BY-SA 4.0。使用或发布衍生标注时必须保留署名和相同方式共享要求。

### `VCSUM`

- 数据集：VCSUM 中文会议摘要数据；
- 本地内容：239 条 `overall_context`，对应 `overall_highlights`；另有 long/short train、dev、test 标注；
- 标注字段：主题切分、标题、分段摘要、整体摘要和重点句；
- 适合验证：长文本摘要、重点句召回、引用覆盖和检索后生成；
- 本地仓库带 MIT `LICENSE`，但原始视频/转写的再分发权仍需按上游说明单独确认，不能仅凭仓库代码许可证推断。

## 当前结论

这批数据已经满足“真实长会议评测”的音频和会议摘要基础条件。机器初标已经完成，但还没有形成经过人工确认的完整问题—答案—引用—待办 gold 真值。当前处理结果是：

1. 先用 `Eval_Ali` 的 TextGrid 作为 ASR 真值；
2. 用 `VCSUM` 的重点句、主题和摘要作为摘要/RAG 真值；
3. 已从会议原文制作问题、答案、引用和待办候选；
4. 已把机器初标记为 `silver`，人工确认后才升级为 `gold`；
5. 正式 gold 集仍需按会议 ID 切分 train/dev/test，不能把同一会议的片段拆到不同集合。

脚本 `backend/scripts/build_real_meeting_candidates.py` 已生成：

- `backend/evaluation/datasets/meetingmind_real_v1_sources.jsonl`：8 个 AliMeeting Eval 会议源记录；
- `backend/evaluation/datasets/meetingmind_real_v1_candidates.jsonl`：26 场 VCSUM 测试会议、158 条问题/答案/引用候选（整体结论和主题问答）。
- `backend/evaluation/datasets/meetingmind_real_v1_review_manifest.json`：文件哈希、数量和人工复核清单。

候选文件明确标记为 `silver`，包含 130 条 VCSUM 和 64 条 AliMeeting 的低置信度待办候选，以及约束候选；它们还没有待办真值，也没有经过人工复核，不能直接当作最终 F1 报告。

## 不提交原始数据的原因

音频文件体积大，且公开数据仍受许可证和再分发条件约束。Git 只保留本说明和最终小型标注索引；原始数据在本机准备好即可运行评测。
