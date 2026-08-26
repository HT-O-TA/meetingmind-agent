"""用同一冻结测试集比较 Prompt-only、Few-shot、LoRA 与 QLoRA。"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

try:
    from .common import (
        build_messages,
        extract_json_array,
        latency_summary,
        load_jsonl,
        score_predictions,
        sha256_file,
        validate_todos,
    )
except ImportError:  # 允许直接执行脚本。
    from common import (
        build_messages,
        extract_json_array,
        latency_summary,
        load_jsonl,
        score_predictions,
        sha256_file,
        validate_todos,
    )


# 负例放在首位，避免小模型对最后一个空数组示例产生明显的近因偏置。
FEW_SHOT_IDS = ("syn-tra-037", "syn-tra-009", "syn-tra-001")


def load_inference_model(base_model: str, protocol: str, adapter: str | None):
    if protocol == "qlora":
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            local_files_only=True,
            dtype=torch.bfloat16,
            quantization_config=quantization,
            device_map={"": 0},
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            base_model, local_files_only=True, dtype=torch.bfloat16
        ).to("cuda")
    if adapter:
        model = PeftModel.from_pretrained(model, adapter, local_files_only=True)
    return model.eval()


def evaluate(
    protocol: str,
    base_model: str,
    dataset_path: str,
    output_path: Path,
    adapter: str | None = None,
    max_new_tokens: int = 320,
) -> dict[str, Any]:
    if protocol not in {"prompt_only", "few_shot", "lora", "qlora"}:
        raise ValueError(f"unsupported protocol: {protocol}")
    if protocol in {"lora", "qlora"} and not adapter:
        raise ValueError(f"{protocol} requires --adapter")
    if protocol in {"prompt_only", "few_shot"} and adapter:
        raise ValueError(f"{protocol} must not use an adapter")
    if not torch.cuda.is_available():
        raise RuntimeError("measured evaluation requires a CUDA GPU")

    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    train_records = load_jsonl(dataset_path, "train")
    test_records = load_jsonl(dataset_path, "test")
    train_by_id = {record["sample_id"]: record for record in train_records}
    few_shots = [train_by_id[sample_id] for sample_id in FEW_SHOT_IDS] if protocol == "few_shot" else []

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model = load_inference_model(base_model, protocol, adapter)
    torch.cuda.synchronize()
    model_load_seconds = time.perf_counter() - load_started
    rows: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for record in test_records:
        messages = build_messages(record, few_shots)
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        torch.cuda.synchronize()
        latency_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(latency_ms)
        raw = tokenizer.decode(generated[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True).strip()
        row = {
            "sample_id": record["sample_id"],
            "expected": record["expected"],
            "raw_output": raw,
            "json_valid": False,
            "schema_valid": False,
            "predicted_validated": [],
            "error": None,
            "latency_ms": latency_ms,
            "input_tokens": int(inputs["input_ids"].shape[1]),
            "output_tokens": int(generated.shape[1] - inputs["input_ids"].shape[1]),
        }
        try:
            parsed = extract_json_array(raw)
            row["json_valid"] = True
            row["predicted_validated"] = validate_todos(parsed)
            row["schema_valid"] = True
        except (ValueError, json.JSONDecodeError) as exc:
            row["error"] = str(exc)
        rows.append(row)

    metrics = score_predictions(rows)
    report = {
        "schema_version": "meetingmind.extraction-evaluation.v1",
        "protocol": protocol,
        "base_model": base_model,
        "evaluation_script_sha256": sha256_file(__file__),
        "common_script_sha256": sha256_file(Path(__file__).with_name("common.py")),
        "base_model_weight_sha256": sha256_file(Path(base_model) / "model.safetensors"),
        "adapter": adapter,
        "adapter_weight_sha256": sha256_file(Path(adapter) / "adapter_model.safetensors") if adapter else None,
        "dataset": dataset_path,
        "dataset_sha256": sha256_file(dataset_path),
        "split": "test",
        "few_shot_ids": list(FEW_SHOT_IDS) if few_shots else [],
        "generation": {"do_sample": False, "max_new_tokens": max_new_tokens, "enable_thinking": False},
        "metrics": metrics,
        "latency": latency_summary(latencies_ms),
        "model_load_seconds": model_load_seconds,
        "peak_cuda_allocated_mb": torch.cuda.max_memory_allocated() / 1024 / 1024,
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "transformers": importlib.metadata.version("transformers"),
            "peft": importlib.metadata.version("peft"),
            "bitsandbytes": importlib.metadata.version("bitsandbytes"),
        },
        "rows": rows,
        "limitations": [
            "16 条测试样本全部为项目自编合成文本，不能代表真实会议效果。",
            "单次确定性生成、单随机种子，无置信区间。",
            "严格字符串指标不奖励语义等价改写。",
            "Few-shot 示例固定且来自训练切分，测试 meeting_id 与训练切分不重叠。",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=("prompt_only", "few_shot", "lora", "qlora"), required=True)
    parser.add_argument("--base-model", default="backend/model/qwen3-0.6B")
    parser.add_argument("--dataset", default="backend/finetuning/data/meeting_todo_synthetic_v1.jsonl")
    parser.add_argument("--adapter")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-new-tokens", type=int, default=320)
    args = parser.parse_args()
    evaluate(args.protocol, args.base_model, args.dataset, args.output, args.adapter, args.max_new_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
