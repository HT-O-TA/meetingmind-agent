# 第二项目：PatchAlign-Cpp 立项与实施路线

> 日期：2026-08-28
>
> 状态：方案已形成，项目尚未创建；模型、数据和指标须在正式开工时再次冻结
>
> 定位：面向 C++ 缺陷修复的可验证小模型后训练与对齐项目
>
> 历史关系：本文细化并替换《六链路架构对标与演进设计（第三版）》中“中文指令遵循与安全拒答”的暂定选题，不倒改前三版历史文档

## 0. 一页结论

第二项目暂定名为：

**PatchAlign-Cpp：面向 C++ 缺陷修复的可验证后训练系统**

项目要回答的核心问题是：

> 在固定数据、提示模板和评测协议下，SFT、DPO 与可选的 RLVR 能否让一个开放权重代码模型更稳定地生成可应用、可编译、通过隐藏测试且改动克制的 C++ 补丁？收益是否伴随格式过拟合、能力退化或奖励投机？

推荐主实验链：

```text
M0：开放权重 Base 模型
→ M1：C++ 缺陷修复 SFT
→ M2：基于 hard preference pairs 的 DPO
→ M3：基于编译和隐藏测试的 RLVR/GRPO（可选）
→ 同协议质量、资源和失败模式对比
```

当前不考虑硬件时，理论首选基座为 `Qwen/Qwen3-Coder-Next-Base`。它是面向代码、适合继续后训练的预训练模型，采用稀疏 MoE 架构，约 80B 总参数、3B 激活参数，原生 256K 上下文并使用 Apache-2.0 许可证。正式开工时仍要根据硬件、训练框架支持和实验周期重新确认，不能把“激活 3B”误解为只需承担 3B 模型的训练成本。

第一版不自行爬取 GitHub 网页。优先组合使用：

- CommitPack/CommitPackFT：真实 C/C++ 修复提交，主要用于 SFT；
- RunBugRun C++ 子集：带测试的短程序缺陷，主要用于可执行训练、DPO 和 RLVR；
- Defects4C：真实 C/C++ 缺陷外部评测；
- SWE-bench Multilingual、Multi-SWE-bench 的 C/C++ 子集：仓库级外部评测。

只有现成数据无法覆盖真实仓库、并发、网络或内存安全缺陷时，才增加基于 GitHub API、选择性 Git clone 和容器重放的数据采集管线。

## 1. 项目在三项目组合中的位置

### 1.1 三个项目分别证明什么

| 项目 | 核心问题 | 主要能力证据 |
|---|---|---|
| MeetingMind | 如何把模型能力变成可靠 AI 应用 | Agent、RAG、上下文、记忆、工具治理、异步任务、评测 |
| PatchAlign-Cpp | 如何通过数据和训练改变并验证模型行为 | 数据工程、SFT、偏好对齐、可验证奖励、消融、推理 |
| C++ 游戏服务器 | 如何构建高性能并发服务 | C++20、Linux 网络、状态同步、内存与性能工程 |

PatchAlign-Cpp 与另外两个项目有联系，但保持独立：

- 不复用 MeetingMind 业务数据，不建设 RAG、会议知识库或 Agent 工作流；
- 不把未来游戏服务器包装为训练平台，也不为了 AI 标签给游戏服务器强加模型；
- 未来可以把游戏服务器中的脱敏缺陷作为额外真实评测，但不得同时进入训练集；
- 微调项目的主要产物是数据、模型 adapter、实验结果和失败分析，不是网页应用。

### 1.2 面向岗位

该项目主要补充以下岗位证据：

- 大模型应用算法或后训练工程；
- LLM 数据工程、评测与对齐；
- 模型工程、训练平台和推理工程；
- 代码智能、自动程序修复相关方向；
- 需要 Python/PyTorch 实验能力，同时重视工程验证的岗位。

个人规模项目不能等同于基础模型团队的大规模预训练或完整 RLHF 生产经验。项目价值来自可复现数据、严谨对照、真实失败分析和清楚的能力边界。

## 2. 任务契约与项目边界

### 2.1 第一阶段任务契约

第一阶段采用“给定定位上下文的补丁生成”，避免一开始变成代码 Agent：

```text
输入：
- 缺陷描述或失败现象
- 已定位的 C++ 文件/函数上下文
- 编译错误、失败测试或运行日志
- 明确的输出约束

输出：
- 仅生成统一 diff，或生成满足固定 JSON Schema 的补丁对象

验证：
- 补丁能否解析和应用
- 修复前是否失败
- 修复后能否编译
- 公开/隐藏测试是否通过
- 是否引入回归或 Sanitizer 错误
- 修改范围是否合理
```

仓库级故障定位和自主工具循环放到后续拓展。若使用 SWE-bench 类固定 harness，只把它作为统一评测环境；不同 checkpoint 必须使用相同 harness，不能把 Agent 框架优化冒充模型训练收益。

### 2.2 第一版明确不做

- 不做完整 RAG 或向量数据库；
- 不做自主代码 Agent、长期记忆和多 Agent；
- 不做复杂前端；
- 不同时追逐 SFT、DPO、PPO、KTO、ORPO、GRPO 等所有方法；
- 不从继续预训练开始；除非后续实验能证明领域知识而非行为对齐才是瓶颈；
- 不以训练 loss 下降作为成功结论；
- 不只使用 LLM-as-a-Judge；
- 不把合成缺陷成绩外推为真实仓库修复能力；
- 不执行未经隔离的不可信代码。

### 2.3 完成定义

项目只有同时具备以下证据才算完成：

1. 冻结的任务 Schema、数据版本、切分清单和基线；
2. 可复现的 M0、M1、M2 对照，M3 为可选拓展；
3. 至少一套可执行测试集和一套仓库隔离的真实外部测试集；
4. 质量指标、资源指标和统计不确定性；
5. 对数据泄漏、能力退化、过拟合和 reward hacking 的检查；
6. 能从新环境执行的数据准备、训练、评测和推理命令；
7. 数据卡、模型卡、实验报告、Bad Case 与真实性声明；
8. 本人能够解释关键实现，不依赖只会修改配置文件的黑盒框架。

## 3. 模型选型

### 3.1 理论首选

不考虑硬件时，首选：

`Qwen/Qwen3-Coder-Next-Base`

选择理由：

- 是预训练 Base checkpoint，便于观察本人 SFT 和偏好对齐带来的变化；
- 代码能力和长上下文能力与 C++ 修复方向匹配；
- 官方定位包含为后训练保留空间；
- Apache-2.0 许可证便于公开 adapter、配置和实验报告；
- 可将官方 post-trained checkpoint 作为外部能力上界。

主要风险：

- 80B 总权重会影响加载、存储、优化器状态和通信成本；
- 512 专家的稀疏 MoE 增加 PEFT target、训练兼容性和实验解释难度；
- 新架构可能需要较新的 Transformers、PEFT、TRL 或专用训练实现；
- 模型预训练数据不可完全审计，外部基准的基础模型污染只能披露，不能声称彻底排除。

### 3.2 备选与各自用途

| 选择 | 适用情况 | 代价 |
|---|---|---|
| Qwen3-Coder-Next-Base | 硬件和框架允许，追求最新代码 Base 与完整后训练链 | MoE 和总参数带来较高复杂度 |
| Qwen3-8B-Base | 希望使用较新的 dense Base，降低 MoE 干扰 | 不是专门的 Coder 系列 |
| Qwen2.5-Coder-7B Base | 希望使用成熟、代码专用、易做 LoRA/QLoRA 的 dense 模型 | 模型代际较旧 |
| 已对齐的 Coder Instruct | 资源不足，只做领域适配和偏好优化 | 无法把已有厂商后训练归为本人成果 |

最终选型不能只比较公开榜单，还要运行小规模 pilot：

- 相同 100～300 条样本；
- 相同上下文长度和 LoRA 配置；
- 比较是否能稳定训练、峰值显存、吞吐和补丁格式；
- 确认评测 harness、推理引擎和 adapter 导出兼容；
- 再冻结模型名、revision、tokenizer、chat template 和依赖版本。

### 3.3 基线角色必须分开

| 角色 | 用途 | 能否作为本人训练起点 |
|---|---|---|
| Base checkpoint | M0 与后续 SFT 起点 | 是 |
| 官方 post-trained/instruct checkpoint | 外部上界或教师模型 | 不作为完整后训练链起点 |
| 闭源强模型 | 辅助生成候选或抽检 | 只能标明来源，不能作为人工真值 |
| 本人 SFT checkpoint | M1、DPO reference 起点 | 是 |

若不同模型需要不同 chat template，应统一任务信息和输出约束，同时保留各模型官方模板。不得因为给某一模型使用更有利的 few-shot 示例而破坏公平比较。

## 4. 数据方案

### 4.1 数据源分工

| 数据源 | 内容 | 推荐用途 | 主要限制 |
|---|---|---|---|
| CommitPack/CommitPackFT | GitHub 提交前后代码、提交信息、文件与许可证元数据 | 真实提交 SFT、仓库级切分 | 很多提交缺少可复现测试，`fix` 标签不等于真实缺陷修复 |
| RunBugRun C++ 子集 | 来自 Project CodeNet 的可执行 buggy/fixed 短程序对、测试和缺陷标签 | 打通训练/执行闭环、DPO 候选、RLVR | 不是现实仓库任务，程序和缺陷分布较受限 |
| Defects4C | 人工确认的真实 C/C++ GitHub 缺陷及可执行验证 | 真实外部测试，原则上不参与训练 | 数据量有限，构建成本高 |
| SWE-bench Multilingual | 多语言真实 issue/PR 修复任务 | C/C++ 仓库级外部测试 | 任务数量有限，harness 较重，可能存在基础模型预训练污染 |
| Multi-SWE-bench | 更大规模的多语言真实仓库任务 | 第二套外部测试 | 需单独审计 C/C++ 子集、许可证和执行成本 |
| NIST SARD | 已知安全弱点的 C/C++ 等程序 | 可选的内存安全/安全修复切片 | 多为合成或模板化安全样本，不能代表一般缺陷 |

### 4.2 第一版数据组合

建议按三个集合建设：

```text
real_commit_sft
  = CommitPackFT 中经许可证、语言、提交质量过滤的 C/C++ 样本

executable_repair_train
  = RunBugRun C++ 子集 + 少量本人审核的受控缺陷变异

external_repo_eval
  = Defects4C + SWE-bench Multilingual/Multi-SWE-bench 的冻结 C/C++ 子集
```

三者不能混淆：

- CommitPackFT 样本没有测试时，只能证明模型学习了修复形式，不能用于“测试通过率”结论；
- RunBugRun 按题目/程序隔离，不得称为仓库隔离；
- 外部仓库评测集中的仓库、fork、mirror 和补丁必须从所有训练源中拉黑；
- 合成缺陷可以训练和诊断，但不能成为唯一测试集。

### 4.3 许可证与来源策略

第一版采用保守白名单：

- Apache-2.0；
- MIT；
- BSD-2-Clause、BSD-3-Clause；
- ISC；
- CC0/Unlicense 在确认来源声明后使用。

GPL、AGPL、LGPL、MPL 和 unknown 不默认进入公开训练数据。是否可以使用、如何分发应单独审查；本文不是法律意见。

每条样本至少保存：

- 数据源和数据集 revision；
- `owner/repo`、canonical upstream 和 commit SHA；
- 原始许可证及确认时间；
- 原文件路径和语言；
- 内容哈希、patch 哈希；
- 数据生成方式：真实提交、程序提交或合成变异；
- train/validation/test 归属及理由；
- 是否具备可执行测试；
- 原始数据是否允许再分发。

大规模原始代码和模型权重不直接提交 GitHub。仓库只保存下载/重建脚本、manifest、小型样例和校验哈希。

### 4.4 样本 Schema

建议统一为可追踪而非只满足训练器的 Schema：

```json
{
  "sample_id": "sha256:...",
  "source": "commitpackft|runbugrun|defects4c|synthetic",
  "source_revision": "...",
  "repository": "owner/name",
  "repository_family": "canonical-owner/canonical-name",
  "commit_before": "...",
  "commit_after": "...",
  "license": "apache-2.0",
  "language": "cpp",
  "bug_type": "bounds|lifetime|concurrency|logic|api|build|unknown",
  "problem": "...",
  "code_context": "...",
  "failure_evidence": "...",
  "gold_patch": "...",
  "public_tests": ["..."],
  "hidden_test_manifest": "...",
  "split": "train|validation|internal_test|external_test",
  "provenance": {
    "synthetic": false,
    "generator": null,
    "review_status": "machine_filtered|human_reviewed"
  }
}
```

训练时再投影为 SFT 或 DPO 所需格式，原始规范化记录保持不变。

## 5. 仓库隔离、防泄漏与数据质量

### 5.1 正确切分顺序

```text
加载原始元数据
→ 规范化 owner/repo 与历史改名
→ 识别 fork、mirror、vendor 和共同上游
→ 生成 repository_family_id
→ 拉黑所有外部 benchmark repository family
→ 按 repository family 分配 train/validation/internal_test
→ 再提取文件、函数、上下文窗口和补丁样本
→ 跨切分相似度去重
→ 冻结 manifest 与哈希
```

禁止先把提交切成函数或窗口，再随机拆分样本。同一仓库的邻近代码、历史版本或 fork 很容易由此泄漏到测试集。

### 5.2 建议测试层次

| 集合 | 隔离方式 | 回答的问题 |
|---|---|---|
| validation | repository family 隔离 | 超参数和 early stopping 是否有效 |
| internal_repo_test | 未见仓库族 | 对相同数据来源的新仓库能否泛化 |
| temporal_test | 同仓库更晚时间，可选 | 是否能适应同一仓库未来缺陷 |
| external_repo_eval | 完全独立数据集和仓库 | 收益能否迁移到真实外部任务 |

仓库隔离测试是主要结论；时间切分只能作为辅助诊断，不能取代未见仓库泛化。

### 5.3 去重层次

至少做：

1. 原文、规范化代码和 diff 的精确哈希；
2. token/shingle MinHash 或 LSH 近似去重；
3. 去除注释、空白和变量名变化后的 AST/结构指纹；
4. fork、镜像仓库和 vendor 目录的仓库族去重；
5. gold patch、issue 文本和测试名的交叉检索；
6. 训练输出中是否复现外部测试 gold patch 的污染审计。

基础模型预训练数据不可审计时，只能声明“已防止本人后训练数据污染，基础模型污染未知”，不能写“完全无污染”。

### 5.4 数据质量过滤

真实提交初筛建议：

- 提交信息或关联 issue 明确描述失败行为；
- 修改集中在有限的 C/C++ 源文件；
- 排除纯格式化、重命名、注释、依赖升级和生成文件；
- 限制过大 diff，超大改动进入单独难例集；
- 修复前后代码都能被解析；
- 可执行样本必须重放“修复前失败、修复后通过”；
- 公开测试和隐藏测试职责分开；
- 按 bug 类型和仓库领域抽样人工复核。

数据规模不应先写死。先用基线错误分布决定增补什么数据，而不是先生成几十万条低质量样本。

## 6. 是否需要自行采集数据

### 6.1 第一版不需要爬虫

不写 GitHub HTML 爬虫。原因是：

- CommitPackFT 已提供大规模真实提交；
- RunBugRun 已提供可执行缺陷与测试；
- Defects4C 和 SWE-bench 系列已提供真实外部评测；
- 第一阶段的主要未知量是训练和评测设计，而不是数据量；
- 过早自采会把时间消耗在 API 限流、构建依赖和许可证清理上。

### 6.2 何时才增加采集管线

满足任一条件再启动：

- 真实 C++ 仓库修复样本明显不足；
- 现有样本无法复现测试；
- 游戏服务器相关的网络、并发、生命周期或内存缺陷覆盖不足；
- 模型在短程序上提高，但无法迁移到真实项目；
- 需要形成具有本人选题特色、可公开复现的数据子集。

### 6.3 推荐采集方式

采集方式是 GitHub API/公开元数据 + Git，而不是网页抓取：

```text
许可证白名单仓库
→ GitHub REST/GraphQL 或公开数据集发现 PR/commit
→ 获取 issue、PR、commit 和父 commit 元数据
→ 浅克隆指定 revision
→ 在无网络容器中构建修复前后版本
→ 验证 before-fail / after-pass
→ 抽取最小上下文、补丁和测试 manifest
→ 人工抽检
→ 写入不可变数据版本
```

候选提交最好同时满足：

- 关联明确 issue 或 PR；
- 包含新增/修改测试；
- 父提交可构建；
- 修复前失败、修复后通过；
- 构建时间和依赖可控；
- 不需要私有服务、密钥或联网环境；
- 仓库许可证和补丁来源可追踪。

## 7. 评测设计

### 7.1 主指标

| 指标 | 含义 |
|---|---|
| patch parse rate | 输出能否解析为规定补丁格式 |
| patch apply rate | 补丁能否应用到目标 revision |
| compile rate | 应用后能否完成构建 |
| public test pass rate | 是否解决已知失败 |
| hidden test pass rate | 是否真正满足未公开约束 |
| regression rate | 原本通过的测试是否被破坏 |
| Pass@1 / Pass@k | 单次或多候选修复成功率 |
| sanitizer pass rate | ASan/UBSan/TSan 是否发现新增问题 |
| patch size | 修改文件数、行数及无关改动比例 |

项目的第一主指标建议为 `hidden test pass rate / Pass@1`，同时以 compile rate、regression rate 和 patch size 作为约束。不能为了提高编译率而接受不解决问题的空补丁。

### 7.2 资源与工程指标

- 峰值 GPU 显存；
- 总训练时长和 GPU-hours；
- 训练 tokens/s 与 samples/s；
- checkpoint、adapter 和合并权重大小；
- 批量推理吞吐；
- 首 token 延迟、P50/P95 延迟；
- 编译/测试沙箱平均耗时和超时率。

### 7.3 统计与可比性

- 所有 checkpoint 使用相同冻结测试集、采样参数和执行环境；
- 保存原始生成结果，不只保存汇总分数；
- Pass@k 报告采样次数、温度和随机种子；
- 对关键比例报告 bootstrap 置信区间；
- 小规模配置/数据消融尽量运行多个随机种子；
- 完整大模型训练若只能运行一次，应明确资源限制，不伪装成稳定结论；
- 在全量训练前冻结“最小有意义提升”和可接受退化阈值。

### 7.4 保留能力与退化

除目标任务外，保留一小套冻结控制集，检查：

- 一般 C++ 代码理解；
- 正常代码生成；
- 非修复类指令遵循；
- 补丁之外的必要解释能力；
- 输出长度、重复和格式僵化；
- 简单问题是否因过度对齐而拒绝回答或只输出 diff。

## 8. 分阶段实施路线

### A0：冻结问题、边界与实验协议

#### 学习目标

- 分清预训练、SFT、偏好优化和强化学习分别改变什么；
- 理解 Base checkpoint 与 Instruct checkpoint 的差别；
- 学会先定义评测再训练。

#### 任务

1. 创建独立仓库，确定项目名、许可证和真实性声明；
2. 冻结第一阶段输入、输出和补丁格式；
3. 选定一个 Base checkpoint 和一个官方 post-trained 上界；
4. 固定生成参数、最大上下文、最大补丁长度；
5. 定义主指标、退化指标和资源指标；
6. 建立实验 ID、配置快照、随机种子和环境记录规则。

#### 验收

- 不训练也能运行一个极小的输入到评分闭环；
- 同一生成结果重复评分得到相同结果；
- 能解释每个指标对应什么失败模式。

### A1：建立数据清单与仓库隔离

#### 学习目标

- 理解训练数据质量、许可证、重复和污染如何改变结论；
- 掌握 repository family、时间切分和外部测试的区别。

#### 任务

1. 下载固定 revision 的公开数据元数据；
2. 建立许可证白名单和 benchmark 仓库黑名单；
3. 规范化仓库、fork、mirror 和历史改名；
4. 按 repository family 切分 CommitPackFT C/C++ 子集；
5. 按题目/程序标识切分 RunBugRun，不伪称仓库隔离；
6. 完成精确与近似去重；
7. 输出数据卡、split manifest 和统计报告；
8. 人工抽检各来源、bug 类型和切分。

#### 验收

- 外部 benchmark 仓库在训练 manifest 中为零；
- 任意样本能回溯来源、许可证和切分原因；
- 重新运行数据构建产生相同哈希；
- 抽检报告包含错误过滤和保留难例。

### A2：先完成冻结基线与执行沙箱

#### 学习目标

- 区分模型失败、补丁协议失败、构建失败和测试失败；
- 理解不可信代码执行的隔离边界。

#### 任务

1. 实现统一 diff/结构化补丁解析和应用；
2. 建立无网络、非特权、限制 CPU/内存/PID/时间/磁盘的执行沙箱；
3. 执行修复前后的构建和测试；
4. 记录每一步退出码、日志和超时原因；
5. 对 M0 Base、Prompt/Few-shot 和官方 post-trained 上界跑同协议基线；
6. 冻结初始评测报告和 Bad Case 分类。

#### 验收

- 恶意或无限循环样本不能影响宿主机；
- 重复执行结果稳定；
- 每个失败都能归入明确阶段；
- 后续训练结果不能覆盖基线原始预测。

### A3：完成 SFT

#### 学习目标

- 掌握 chat/completion 模板、tokenization、label masking、packing、梯度累积和 checkpoint；
- 理解 LoRA rank、target modules、学习率与数据组成的影响；
- 理解 LoRA 和 QLoRA 的质量/资源权衡。

#### 任务

1. 将规范数据投影为训练格式；
2. 实现或读懂核心训练链，不只调用一键式 GUI；
3. 先进行过拟合小批次测试，证明 loss 和样本对齐正确；
4. 进行小规模学习率、rank、上下文长度试验；
5. 冻结正式 SFT 配置并训练 M1；
6. 运行与 M0 完全相同的评测；
7. 分析格式正确率、编译率、隐藏测试和能力退化。

#### 验收

- checkpoint 能恢复、导出并独立推理；
- 训练 mask、padding 和 EOS 行为有自动测试；
- M1 的收益能对应到具体数据类型；
- 报告失败配置，而非只保留最佳结果。

### A4：构造偏好数据

#### 学习目标

- 理解偏好数据不是简单的“标准答案/随机错误答案”；
- 掌握 hard pair、标注噪声和偏好强度问题。

#### 任务

1. 用 M1 对同一缺陷采样多个候选；
2. 通过补丁应用、编译、公开/隐藏测试、Sanitizer 和修改规模评分；
3. 生成 `prompt/chosen/rejected`，保留完整评分依据；
4. 优先选择 hard pair：两个候选都看似合理但真实质量不同；
5. 排除只靠长度、格式或明显编译错误即可区分的低价值 pair；
6. 按分数差、bug 类型和仓库分层抽检；
7. 冻结偏好数据卡和版本。

#### 典型 hard pair

- 两个补丁都能编译，只有一个通过隐藏测试；
- 两个都通过公开测试，一个破坏历史测试；
- 两个都解决当前错误，一个引入越界或资源泄漏；
- 两个逻辑都正确，一个进行了大规模无关重构；
- 一个硬编码公开测试，另一个实现一般化修复。

#### 验收

- chosen/rejected 来自同一输入和可比采样条件；
- 每个偏好有机器证据或人工复核依据；
- 不把模型生成和模型自评包装为人类偏好真值；
- 统计简单 pair 与 hard pair 比例。

### A5：完成 DPO

#### 学习目标

- 理解 reference model、beta、chosen/rejected log-prob 和长度偏差；
- 观察偏好优化的收益与副作用。

#### 任务

1. 以冻结 M1 作为 DPO 起点和 reference；
2. 先在小数据上验证 loss、log-prob 和 adapter 保存；
3. 运行少量 beta/学习率消融；
4. 训练 M2；
5. 用同协议比较 M0、M1、M2；
6. 检查 chosen/rejected margin、输出长度和多样性；
7. 分析 DPO 是否提高隐藏测试，同时损害一般能力或导致补丁保守化。

#### 验收

- M2 的提升不能只来自输出更短或格式更固定；
- 目标指标和保留能力都被报告；
- DPO 失败时能够判断是数据、beta、reference 还是评测问题；
- 不因 DPO 没有提升而删除负面结果。

### A6：可选 RLVR/GRPO

只有 A0～A5 稳定后进入本阶段。DPO 已形成完整项目时，GRPO 不是必做项。

#### 进入条件

- 沙箱可靠；
- 奖励可确定重放；
- 同一 prompt 能产生质量有差异的候选；
- 隐藏测试足以防止简单投机；
- 预算允许在线采样和多候选执行。

#### 建议奖励

```text
reward
= patch_parse
+ patch_apply
+ compile
+ public_tests
+ hidden_tests
+ sanitizer
- regression
- unrelated_changes
- excessive_patch_size
- timeout_or_resource_abuse
```

奖励值需在 pilot 后冻结。关键是优先级而非简单相加：隐藏测试和回归应比格式、长度等表层指标重要。

#### 必测 reward hacking

- 删除或跳过测试；
- 修改构建脚本绕过目标；
- 永远返回固定值；
- 捕获并吞掉异常；
- 硬编码公开测试输入；
- 禁用 Sanitizer 或断言；
- 利用超时、文件系统或网络副作用。

#### 验收

- M3 必须在未参与奖励的隐藏测试上验证；
- 报告奖励、KL、长度、熵和任务指标的共同变化；
- 若收益不足以抵消复杂度，保留 DPO 作为最终方案。

### A7：推理、消融和失败分析

#### 学习目标

- 把训练产物转化为可部署、可测量的模型服务；
- 学会用消融而不是故事解释结果。

#### 任务

1. 使用 vLLM 或兼容引擎加载 Base + adapter；
2. 提供最小批量推理入口和可选 OpenAI-compatible API；
3. 测试 adapter 合并与不合并的质量一致性；
4. 测量吞吐、显存和 P50/P95 延迟；
5. 完成核心消融；
6. 建立 Bad Case 浏览和归因报告。

建议消融优先级：

1. Base vs SFT vs SFT+DPO；
2. 真实提交数据 vs 可执行短程序数据 vs 混合；
3. 随机样本切分 vs 仓库族切分，用于展示泄漏影响；
4. 简单偏好对 vs hard preference pairs；
5. LoRA vs QLoRA，重点比较质量、显存和时间；
6. 有无隐藏测试/回归惩罚的奖励设计。

#### 验收

- 新环境可以根据文档加载 adapter 并复现一小组结果；
- 服务性能与离线质量使用相同 checkpoint 标识；
- 失败按数据、模型、补丁、编译、测试和基础设施分类；
- 报告包含至少三个有代表性的反例及修订过程。

### A8：最终交付与求职证据

最终仓库应包含：

- 架构和任务说明；
- 数据卡、许可证清单、切分和去重报告；
- 训练配置及环境锁定；
- SFT、DPO 与可选 RLVR 脚本；
- 安全执行沙箱；
- 冻结评测集 manifest 和评测器；
- M0/M1/M2/M3 原始预测和对比报告；
- adapter/model card；
- 推理与性能报告；
- Bad Case、失败实验和真实性声明；
- 一条最小复现命令和一个短 Demo。

验收完成后再写简历数字，不能提前填写。

## 9. 推荐仓库结构

```text
patchalign-cpp/
├── README.md
├── pyproject.toml
├── configs/
│   ├── data/
│   ├── model/
│   ├── train/
│   └── eval/
├── src/patchalign/
│   ├── data/
│   ├── training/
│   ├── preference/
│   ├── evaluation/
│   ├── sandbox/
│   └── serving/
├── scripts/
├── tests/
│   ├── unit/
│   ├── contracts/
│   └── integration/
├── data/
│   ├── manifests/
│   ├── samples/
│   └── README.md
├── reports/
├── docs/
└── artifacts/                 # 默认不提交大模型和大数据
```

配置管理可以使用 YAML/Hydra，也可以保持简单 dataclass + YAML。优先保证配置可追踪，不为了展示技术栈引入复杂配置框架。

## 10. 推荐技术栈

| 领域 | 第一选择 | 说明 |
|---|---|---|
| 训练 | PyTorch、Transformers、Datasets | 核心训练和数据接口 |
| 参数高效微调 | PEFT、bitsandbytes | LoRA/QLoRA |
| 对齐 | TRL | SFT、DPO，后续可选 GRPO |
| 分布式 | Accelerate；需要时 DeepSpeed | 不在单卡阶段提前复杂化 |
| 推理 | vLLM | adapter、批量推理和服务 |
| 实验追踪 | MLflow 或 W&B 二选一 | 配置、指标、artifact |
| 数据版本 | manifest + hash；规模增加后可选 DVC | Git 不存大数据 |
| C++ 构建 | CMake/Ninja、GCC/Clang | 多编译器验证 |
| 动态检查 | ASan、UBSan；并发切片可选 TSan | 安全和未定义行为检查 |
| 执行隔离 | rootless container/Bubblewrap | 禁网和资源限制 |
| 测试与 CI | pytest、轻量编译样例 | CI 不运行昂贵全量训练 |

LLaMA-Factory、ms-swift 等工具可用于环境烟测或结果交叉验证，但本人至少要掌握并能够解释 TRL/PEFT 主训练链中的数据模板、loss mask、LoRA 注入、reference model 和评测调用。

## 11. 测试与 CI

CI 只运行低成本门禁：

- Schema 和配置校验；
- 数据 manifest 哈希和外部仓库黑名单；
- SFT/DPO 样本投影；
- tokenizer、label mask、padding、EOS 合同；
- 补丁解析与应用；
- 小型 C++ 编译/测试沙箱；
- 指标计算与报告生成；
- 固定极小模型/伪 logits 的训练器接口测试。

GPU 全量训练不放入普通 CI。训练任务应输出不可变 run manifest：

```text
run_id
git_commit
model_id + revision
dataset_version + hash
config_hash
environment/container digest
random_seed
checkpoint hashes
prediction artifact hashes
```

## 12. 主要风险与应对

| 风险 | 表现 | 应对 |
|---|---|---|
| 数据泄漏 | 随机切分得分很高，未见仓库骤降 | repository family 切分、benchmark 黑名单、近似去重 |
| 基础模型污染 | 模型复现公开 gold patch | 披露未知污染、增加本人后续采集的时间外测试 |
| 合成数据过于简单 | mutation 测试提高，真实缺陷无收益 | 真实提交训练 + 真实外部评测并列 |
| `fix` 提交噪声 | SFT 学到无关重构 | 提交过滤、人工抽检、可执行验证子集 |
| DPO 偏好过于简单 | 格式提升但隐藏测试不变 | hard pairs、长度匹配、隐藏测试和回归证据 |
| reward hacking | 删除测试、硬编码、绕过构建 | 隐藏测试、只读测试、限制可改路径、独立回归集 |
| 能力退化 | 只会输出短补丁或格式僵化 | 冻结保留能力集、混合数据、控制 beta/学习率 |
| MoE 工程分散精力 | 大量时间花在框架兼容 | pilot 后允许改用 dense Base，记录决策依据 |
| 不可信代码风险 | 无限循环、fork bomb、文件破坏 | 禁网、非特权、只读输入、cgroup/ulimit、超时 |
| 项目范围膨胀 | 再做 Agent、RAG、前端 | 固守给定上下文的补丁生成主任务 |

## 13. 本人学习检查点

每完成一个阶段，应能不看文档回答：

### 数据

- 为什么仓库族切分比随机样本切分严格？
- fork、vendor 和历史版本为什么会造成泄漏？
- CommitPackFT 和 RunBugRun 分别能支持什么结论？
- 为什么基础模型污染只能披露、不能完全排除？

### SFT/PEFT

- causal LM 的 labels 如何构造，哪些 token 应 mask？
- LoRA 的 rank、alpha、target modules 分别影响什么？
- QLoRA 的 4-bit 权重、计算 dtype 和 adapter 是什么关系？
- gradient accumulation、checkpointing 和 packing 如何影响资源与训练？

### DPO

- chosen/rejected 为什么必须共享同一 prompt？
- reference model 和 beta 分别控制什么？
- 为什么简单错误 pair 可能只训练格式和长度？
- 如何发现 DPO 导致的一般能力退化？

### RLVR

- 为什么代码修复比主观对话更适合可验证奖励？
- 公开测试和隐藏测试为什么必须分开？
- 模型可能怎样利用奖励漏洞？
- 什么情况下应停止 GRPO，保留 DPO 作为最终方案？

### 评测与工程

- compile rate、public pass 和 hidden pass 为什么不能互相替代？
- Pass@1 与 Pass@k 分别说明什么？
- 怎样保证一次训练结果可复现？
- 为什么模型提升和 Agent/harness 提升必须分开归因？

## 14. 简历占位写法

在获得真实实验结果后，可按以下结构改写：

> **PatchAlign-Cpp｜面向 C++ 缺陷修复的可验证小模型后训练系统**
> 基于公开 C/C++ 修复提交与可执行缺陷构建带许可证和来源追踪的数据管线，按 repository family 切分并通过精确/近似代码去重隔离外部评测仓库；基于 QLoRA 完成 SFT，利用编译、隐藏测试、回归和补丁规模构造 hard preference pairs 进行 DPO，使冻结测试集 Pass@1 从 `X%` 提升至 `Y%`，同时将回归率控制在 `Z%`；建立无网络资源受限的 C++ 补丁执行沙箱，并通过 vLLM 完成 adapter 部署及显存、吞吐和 P95 延迟评测。

`X/Y/Z` 必须来自冻结报告。若没有统计显著提升，应如实改写为数据管线、方法比较和失败结论，不能补造收益。

## 15. 正式开工前需要确认的事项

以下决定当前不必完成，但创建新仓库前必须确认：

1. GPU 型号、单卡显存、卡数和可占用时长；
2. 是否能使用外部模型 API 辅助生成候选；
3. 可接受的数据下载和本地存储规模；
4. 是否公开 adapter、训练数据派生物和完整预测；
5. 第一阶段只做函数级修复，还是加入给定文件上下文的补丁；
6. 主基座是否继续使用 Qwen3-Coder-Next-Base，或在 pilot 后换成 dense 模型；
7. 是否把 GRPO/RLVR 列为必做；默认答案为否；
8. 未来 C++ 游戏服务器是否只作为外部评测来源；默认答案为是。

## 16. 推荐执行顺序

当前总顺序不变：

```text
MeetingMind 六链路逐层翻新
→ MeetingMind 重大缺陷收口与真实演示
→ 创建 PatchAlign-Cpp 独立仓库
→ A0～A2：任务、数据、基线和沙箱
→ A3：SFT
→ A4～A5：偏好数据与 DPO
→ A6：按证据决定是否做 RLVR/GRPO
→ A7～A8：推理、消融、报告和简历证据
→ C++ 游戏服务器独立立项
```

在 MeetingMind 尚未完成时，可以阅读论文、熟悉 PyTorch/TRL 和设计数据 Schema，但不应同时启动大规模训练与第三个项目开发。

## 17. 参考资料

- [Qwen3-Coder-Next-Base 模型卡](https://huggingface.co/Qwen/Qwen3-Coder-Next-Base)：模型架构、参数、上下文、许可证与后训练定位。
- [Qwen3-Coder 官方微调示例](https://github.com/QwenLM/qwen3-coder/tree/main/finetuning)：官方 SFT 数据格式与训练入口参考。
- [Hugging Face PEFT LoRA](https://huggingface.co/docs/peft/main/conceptual_guides/lora)：LoRA 原理和主要配置。
- [Hugging Face PEFT 量化训练](https://huggingface.co/docs/peft/developer_guides/quantization)：QLoRA 和 4-bit 训练。
- [Hugging Face TRL](https://huggingface.co/docs/trl/en/index)：SFT、DPO、GRPO 等后训练实现。
- [DPO 论文](https://arxiv.org/abs/2305.18290)：直接偏好优化的目标与动机。
- [DeepSeekMath/GRPO 论文](https://arxiv.org/abs/2402.03300)：GRPO 与可验证推理任务背景。
- [CommitPack 数据卡](https://huggingface.co/datasets/bigcode/commitpack)：真实 Git 提交数据、字段和许可证信息。
- [RunBugRun](https://github.com/giganticode/run_bug_run)：带测试的可执行多语言程序修复数据。
- [Defects4C](https://sites.google.com/view/defects4c/home)：真实 C/C++ 缺陷与可执行评测。
- [SWE-bench Multilingual](https://www.swebench.com/multilingual.html)：多语言真实仓库级任务。
- [Multi-SWE-bench](https://github.com/multi-swe-bench/)：更大规模多语言仓库级评测。
- [NIST SARD](https://www.nist.gov/publications/software-assurance-reference-dataset-thousands-programs-known-bugs)：已知安全弱点程序数据。
- [vLLM LoRA](https://docs.vllm.ai/en/latest/features/lora/)：adapter 推理与服务。
- [DeepSpeed ZeRO](https://deepspeed.readthedocs.io/en/stable/zero3.html)：大模型训练内存优化。

## 18. 当前决策摘要

| 决策 | 当前结论 |
|---|---|
| 第二项目题目 | PatchAlign-Cpp：C++ 缺陷修复可验证后训练 |
| 项目主语言 | Python；C++ 用于训练样本、编译与测试环境 |
| 理论首选基座 | Qwen3-Coder-Next-Base |
| 必做训练链 | Base → SFT → DPO |
| 可选拓展 | RLVR/GRPO，仅在可靠奖励和预算成立时进行 |
| 第一版数据 | CommitPackFT + RunBugRun C++ |
| 外部评测 | Defects4C + SWE-bench/Multi-SWE-bench C/C++ |
| 仓库隔离 | repository family 先切分，样本后生成 |
| 是否需要爬虫 | 第一版不需要；后续只做 API + Git + 容器重放采集 |
| 是否建设 Agent/RAG/前端 | 否 |
| 是否修改前三版历史文档 | 否 |
