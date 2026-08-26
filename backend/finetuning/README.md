# 待办抽取 LoRA / QLoRA 实验

该目录是独立学习实验，不默认进入 MeetingMind 线上主链路。目标是把“数据 → 训练 → 公平评测 → 推理”做成可复现证据，而不是提交大模型权重或用合成分数宣传真实业务效果。

## 目录

```text
finetuning/
├── build_dataset.py          # 确定性数据生成和隐私/泄漏检查
├── common.py                 # Prompt、严格 Schema、指标
├── train_adapter.py          # 同一训练循环支持 LoRA / QLoRA
├── evaluate.py               # 四组协议逐条生成
├── summarize_results.py      # 汇总 JSON 和 Markdown
├── infer_todos.py            # 单条推理 Demo
├── configs/                  # 冻结配置
├── data/                     # 合成数据、manifest、数据卡
├── reports/                  # 真实运行报告和逐条输出
└── artifacts/                # 本地 adapter 权重，gitignored
```

## 环境

本次实测环境：RTX 3060 12GB、PyTorch 2.11.0+cu126、Transformers 5.12.1、PEFT 0.18.1、bitsandbytes 0.47.0。PyTorch 应按本机 CUDA 版本安装，再安装：

```bash
python -m venv backend/.venv-ft
source backend/.venv-ft/bin/activate
pip install -r backend/requirements-finetuning.txt
```

基座模型不提交 Git。将官方 `Qwen/Qwen3-0.6B` 放到：

```text
backend/model/qwen3-0.6B
```

本地模型卡和权重许可证均保留在该目录。本实验关闭 thinking，使用确定性生成，减少抽取任务的格式波动。

## 完整复现

所有命令在项目根目录执行：

```bash
backend/.venv-ft/bin/python backend/finetuning/build_dataset.py

backend/.venv-ft/bin/python backend/finetuning/train_adapter.py \
  --config backend/finetuning/configs/lora_qwen3_0.6b.json

backend/.venv-ft/bin/python backend/finetuning/train_adapter.py \
  --config backend/finetuning/configs/qlora_qwen3_0.6b.json
```

四组评测必须使用同一数据文件、`test` 切分、系统 Prompt、生成参数和严格 Schema：

```bash
backend/.venv-ft/bin/python backend/finetuning/evaluate.py \
  --protocol prompt_only --max-new-tokens 240 \
  --output backend/finetuning/reports/prompt_only_eval_20260826.json

backend/.venv-ft/bin/python backend/finetuning/evaluate.py \
  --protocol few_shot --max-new-tokens 240 \
  --output backend/finetuning/reports/few_shot_eval_20260826.json

backend/.venv-ft/bin/python backend/finetuning/evaluate.py \
  --protocol lora --max-new-tokens 240 \
  --adapter backend/finetuning/artifacts/qwen3-0.6b-todo-lora \
  --output backend/finetuning/reports/lora_eval_20260826.json

backend/.venv-ft/bin/python backend/finetuning/evaluate.py \
  --protocol qlora --max-new-tokens 240 \
  --adapter backend/finetuning/artifacts/qwen3-0.6b-todo-qlora \
  --output backend/finetuning/reports/qlora_eval_20260826.json

backend/.venv-ft/bin/python backend/finetuning/summarize_results.py
```

## 推理 Demo

```bash
backend/.venv-ft/bin/python backend/finetuning/infer_todos.py \
  --protocol lora \
  --adapter backend/finetuning/artifacts/qwen3-0.6b-todo-lora \
  --source-id demo-001 \
  --text $'[00:08.00] 成员乙: 请成员丙在周五前整理发布核对表。'
```

脚本同时返回原始文本、严格 Schema 状态和规范化待办。Schema 失败以退出码 2 结束，适合接入烟测。

## 权重与可核验性

两个 adapter 各约 19.3 MiB，保存在 `artifacts/`，默认不提交 Git。训练报告提交以下证据：

- 配置、数据集、基座权重和 adapter 权重 SHA-256；
- 训练/验证样本数、optimizer steps 和可训练参数；
- 每轮 loss、训练时长、训练峰值显存和硬件；
- 明确的数据和实验局限。

如果要在另一台机器复核当前报告，需要重新训练；只要 adapter 哈希不同，就不应声称复现了同一权重。生产分发应使用 Git LFS 或模型仓库，并同时发布模型卡，而不是直接把权重塞进普通 Git 历史。

## 技术依据

- [Qwen3-0.6B 官方模型卡](https://huggingface.co/Qwen/Qwen3-0.6B)
- [PEFT 量化训练指南](https://huggingface.co/docs/peft/developer_guides/quantization)
- [Transformers bitsandbytes / NF4 文档](https://huggingface.co/docs/transformers/quantization/bitsandbytes)
- [AliMeeting4MUG 官方任务说明](https://github.com/alibaba-damo-academy/SpokenNLP/blob/main/alimeeting4mug/readme.md)
