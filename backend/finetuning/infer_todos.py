"""单条会议片段推理 Demo；输出原始结果以及严格 Schema 校验结果。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer

try:
    from .common import build_messages, extract_json_array, validate_todos
    from .evaluate import load_inference_model
except ImportError:  # 允许直接执行脚本。
    from common import build_messages, extract_json_array, validate_todos
    from evaluate import load_inference_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--source-id", default="demo-001")
    parser.add_argument("--protocol", choices=("prompt_only", "lora", "qlora"), default="lora")
    parser.add_argument("--base-model", default="backend/model/qwen3-0.6B")
    parser.add_argument("--adapter")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.protocol in {"lora", "qlora"} and not args.adapter:
        parser.error("LoRA/QLoRA 推理必须提供 --adapter")
    record = {
        "sample_id": args.source_id,
        "source_type": "demo_input",
        "transcript": args.text,
    }
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    model = load_inference_model(args.base_model, args.protocol, args.adapter)
    prompt = tokenizer.apply_chat_template(
        build_messages(record), tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        generated = model.generate(
            **inputs, max_new_tokens=320, do_sample=False, pad_token_id=tokenizer.eos_token_id
        )
    raw = tokenizer.decode(generated[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True).strip()
    result = {"raw_output": raw, "schema_valid": False, "todos": [], "error": None}
    try:
        result["todos"] = validate_todos(extract_json_array(raw))
        result["schema_valid"] = True
    except (ValueError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["schema_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
