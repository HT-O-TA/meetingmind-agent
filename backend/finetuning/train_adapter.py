"""使用 Transformers + PEFT 运行可复现的 LoRA/QLoRA 教学实验。"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import random
import time
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

try:
    from .common import build_messages, expected_json, load_jsonl, sha256_file
except ImportError:  # 允许直接执行脚本。
    from common import build_messages, expected_json, load_jsonl, sha256_file


class SupervisedChatDataset(Dataset):
    def __init__(self, records: list[dict[str, Any]], tokenizer: Any, max_length: int):
        self.examples: list[dict[str, list[int]]] = []
        for record in records:
            messages = build_messages(record)
            prompt_encoded = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            full_encoded = tokenizer.apply_chat_template(
                messages + [{"role": "assistant", "content": expected_json(record)}],
                tokenize=True,
                add_generation_prompt=False,
                enable_thinking=False,
            )
            prompt_ids = list(prompt_encoded["input_ids"])
            full_ids = list(full_encoded["input_ids"])
            if full_ids[: len(prompt_ids)] != prompt_ids:
                raise ValueError(f"chat template prefix mismatch: {record['sample_id']}")
            if len(full_ids) > max_length:
                raise ValueError(
                    f"sample {record['sample_id']} has {len(full_ids)} tokens, above max_length={max_length}; "
                    "refuse silent truncation"
                )
            labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :]
            self.examples.append({"input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels})

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        return self.examples[index]


def make_collator(pad_token_id: int):
    def collate(rows: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        max_length = max(len(row["input_ids"]) for row in rows)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for row in rows:
            padding = max_length - len(row["input_ids"])
            batch["input_ids"].append(row["input_ids"] + [pad_token_id] * padding)
            batch["attention_mask"].append(row["attention_mask"] + [0] * padding)
            batch["labels"].append(row["labels"] + [-100] * padding)
        return {name: torch.tensor(values, dtype=torch.long) for name, values in batch.items()}

    return collate


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def mean_loss(model: Any, loader: DataLoader, device: torch.device) -> float:
    model.eval()
    losses: list[float] = []
    with torch.inference_mode():
        for batch in loader:
            batch = {name: value.to(device) for name, value in batch.items()}
            losses.append(float(model(**batch).loss.detach().float().cpu()))
    model.train()
    return sum(losses) / len(losses) if losses else 0.0


def load_model(config: dict[str, Any], device: torch.device):
    method = config["method"]
    if method == "qlora":
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=config["bnb_4bit_quant_type"],
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=config["bnb_4bit_use_double_quant"],
        )
        model = AutoModelForCausalLM.from_pretrained(
            config["base_model"],
            local_files_only=True,
            dtype=torch.bfloat16,
            quantization_config=quantization,
            device_map={"": device.index or 0},
        )
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    elif method == "lora":
        model = AutoModelForCausalLM.from_pretrained(
            config["base_model"], local_files_only=True, dtype=torch.bfloat16
        ).to(device)
    else:
        raise ValueError(f"unsupported method: {method}")
    model.config.use_cache = False
    lora = LoraConfig(
        r=config["lora_r"],
        lora_alpha=config["lora_alpha"],
        lora_dropout=config["lora_dropout"],
        target_modules=config["target_modules"],
        task_type="CAUSAL_LM",
        bias="none",
    )
    return get_peft_model(model, lora)


def train(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not torch.cuda.is_available():
        raise RuntimeError("this measured experiment requires a CUDA GPU")
    if config.get("compute_dtype") != "bfloat16" or not torch.cuda.is_bf16_supported():
        raise RuntimeError("configured bfloat16 is not supported by this GPU")
    set_seed(config["seed"])
    device = torch.device("cuda", 0)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(device)
    started = time.perf_counter()

    tokenizer = AutoTokenizer.from_pretrained(config["base_model"], local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    train_records = load_jsonl(config["dataset"], "train")
    validation_records = load_jsonl(config["dataset"], "validation")
    train_dataset = SupervisedChatDataset(train_records, tokenizer, config["max_length"])
    validation_dataset = SupervisedChatDataset(validation_records, tokenizer, config["max_length"])
    generator = torch.Generator().manual_seed(config["seed"])
    collator = make_collator(tokenizer.pad_token_id)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config["batch_size"],
        shuffle=True,
        generator=generator,
        collate_fn=collator,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=config["batch_size"],
        shuffle=False,
        collate_fn=collator,
    )

    model = load_model(config, device)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    trainable_parameters = sum(parameter.numel() for parameter in trainable)
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    optimizer = torch.optim.AdamW(
        trainable,
        lr=config["learning_rate"],
        weight_decay=config["weight_decay"],
    )
    initial_validation_loss = mean_loss(model, validation_loader, device)
    optimizer_steps = 0
    loss_history: list[dict[str, float | int]] = []
    gradient_accumulation = config["gradient_accumulation_steps"]
    optimizer.zero_grad(set_to_none=True)
    model.train()
    for epoch in range(config["epochs"]):
        epoch_losses: list[float] = []
        for batch_index, batch in enumerate(train_loader):
            batch = {name: value.to(device) for name, value in batch.items()}
            loss = model(**batch).loss
            (loss / gradient_accumulation).backward()
            epoch_losses.append(float(loss.detach().float().cpu()))
            is_boundary = (batch_index + 1) % gradient_accumulation == 0 or batch_index + 1 == len(train_loader)
            if is_boundary:
                torch.nn.utils.clip_grad_norm_(trainable, config["max_grad_norm"])
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                optimizer_steps += 1
        validation_loss = mean_loss(model, validation_loader, device)
        loss_history.append(
            {
                "epoch": epoch + 1,
                "train_loss": sum(epoch_losses) / len(epoch_losses),
                "validation_loss": validation_loss,
            }
        )

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    model.config.use_cache = True
    model.save_pretrained(output_dir, safe_serialization=True)
    tokenizer.save_pretrained(output_dir)
    torch.cuda.synchronize()
    duration_seconds = time.perf_counter() - started
    adapter_path = output_dir / "adapter_model.safetensors"
    report = {
        "schema_version": "meetingmind.training-report.v1",
        "method": config["method"],
        "status": "completed",
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "training_script_sha256": sha256_file(__file__),
        "common_script_sha256": sha256_file(Path(__file__).with_name("common.py")),
        "dataset_path": config["dataset"],
        "dataset_sha256": sha256_file(config["dataset"]),
        "base_model": config["base_model"],
        "base_model_weight_sha256": sha256_file(Path(config["base_model"]) / "model.safetensors"),
        "adapter_path": str(output_dir),
        "adapter_weight_sha256": sha256_file(adapter_path),
        "adapter_size_bytes": adapter_path.stat().st_size,
        "train_samples": len(train_records),
        "validation_samples": len(validation_records),
        "optimizer_steps": optimizer_steps,
        "trainable_parameters": trainable_parameters,
        "total_parameters_visible": total_parameters,
        "trainable_ratio": trainable_parameters / total_parameters,
        "initial_validation_loss": initial_validation_loss,
        "final_validation_loss": loss_history[-1]["validation_loss"],
        "loss_history": loss_history,
        "duration_seconds": duration_seconds,
        "peak_cuda_allocated_mb": torch.cuda.max_memory_allocated(device) / 1024 / 1024,
        "hardware": {
            "gpu": torch.cuda.get_device_name(device),
            "gpu_total_memory_mb": torch.cuda.get_device_properties(device).total_memory / 1024 / 1024,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "transformers": importlib.metadata.version("transformers"),
            "peft": importlib.metadata.version("peft"),
            "accelerate": importlib.metadata.version("accelerate"),
            "bitsandbytes": importlib.metadata.version("bitsandbytes"),
        },
        "config": config,
        "limitations": [
            "训练集为确定性模板生成的合成数据，指标不能外推到真实会议。",
            "单卡单次实验未做多随机种子置信区间。",
            "adapter 权重保存在 gitignored artifacts，仓库只提交哈希与报告。",
        ],
    }
    report_path = Path(config["report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    train(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
