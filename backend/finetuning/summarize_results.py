"""汇总四组公平评测和两组训练成本，生成可提交的 JSON/Markdown 报告。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import sha256_file
except ImportError:
    from common import sha256_file


EVAL_NAMES = ("prompt_only", "few_shot", "lora", "qlora")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-dir", type=Path, default=Path("backend/finetuning/reports"))
    parser.add_argument("--date", default="20260826")
    args = parser.parse_args()
    eval_reports = {
        name: args.reports_dir / f"{name}_eval_{args.date}.json" for name in EVAL_NAMES
    }
    training_reports = {
        name: args.reports_dir / f"{name}_training_{args.date}.json" for name in ("lora", "qlora")
    }
    evaluations = {}
    for name, path in eval_reports.items():
        report = json.loads(path.read_text(encoding="utf-8"))
        metrics = report["metrics"]
        evaluations[name] = {
            "json_valid_rate": metrics["json_valid_rate"],
            "schema_valid_rate": metrics["schema_valid_rate"],
            "sample_exact_match": metrics["sample_exact_match"],
            "business_field_f1": metrics["business_field_micro"]["f1"],
            "item_exact_f1": metrics["item_exact"]["f1"],
            "hallucinated_business_field_rate": metrics["hallucinated_business_field_rate"],
            "latency_mean_ms": report["latency"]["mean_ms"],
            "latency_p95_ms": report["latency"]["p95_ms"],
            "peak_cuda_allocated_mb": report["peak_cuda_allocated_mb"],
            "source_report": str(path),
            "source_report_sha256": sha256_file(path),
        }
    training = {}
    for name, path in training_reports.items():
        report = json.loads(path.read_text(encoding="utf-8"))
        training[name] = {
            "duration_seconds": report["duration_seconds"],
            "peak_cuda_allocated_mb": report["peak_cuda_allocated_mb"],
            "initial_validation_loss": report["initial_validation_loss"],
            "final_validation_loss": report["final_validation_loss"],
            "trainable_parameters": report["trainable_parameters"],
            "adapter_size_bytes": report["adapter_size_bytes"],
            "adapter_weight_sha256": report["adapter_weight_sha256"],
            "source_report": str(path),
            "source_report_sha256": sha256_file(path),
        }
    summary = {
        "schema_version": "meetingmind.finetuning-comparison.v1",
        "dataset_scope": "76 project-authored synthetic samples; fixed 16-sample test split",
        "evaluations": evaluations,
        "training": training,
        "conclusions": [
            f"LoRA achieved the highest business-field F1 ({evaluations['lora']['business_field_f1']:.4f}) on this synthetic test split.",
            f"QLoRA business-field F1 was {evaluations['qlora']['business_field_f1']:.4f}; it used less inference allocated memory but was slower here.",
            f"Few-shot improved schema validity to {evaluations['few_shot']['schema_valid_rate']:.4f}, but business-field F1 remained {evaluations['few_shot']['business_field_f1']:.4f}.",
            "These results demonstrate a reproducible training pipeline, not real-meeting generalization.",
        ],
        "limitations": [
            "All samples are deterministic, project-authored synthetic text and are not human reviewed.",
            "The test split contains 16 samples and shares language templates with training.",
            "One seed and one run per method; no confidence interval or significance test.",
            "CUDA allocated memory is a process-level measurement and QLoRA visible parameter counts are not directly comparable to BF16 LoRA.",
        ],
    }
    json_path = args.reports_dir / f"comparison_{args.date}.json"
    markdown_path = args.reports_dir / f"comparison_{args.date}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Prompt / Few-shot / LoRA / QLoRA 合成集对比",
        "",
        "> 仅限 76 条项目自编合成样本（测试 16 条），不能外推到真实会议。",
        "",
        "| 协议 | JSON合法率 | Schema合法率 | 样本严格匹配 | 业务字段F1 | 待办项F1 | 幻觉字段率* | 平均延迟ms | P95ms | 推理峰值MiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {"prompt_only": "Prompt-only", "few_shot": "3-shot", "lora": "LoRA", "qlora": "QLoRA"}
    for name in EVAL_NAMES:
        row = evaluations[name]
        lines.append(
            f"| {labels[name]} | {row['json_valid_rate']:.3f} | {row['schema_valid_rate']:.3f} | "
            f"{row['sample_exact_match']:.3f} | {row['business_field_f1']:.3f} | {row['item_exact_f1']:.3f} | "
            f"{row['hallucinated_business_field_rate']:.3f} | {row['latency_mean_ms']:.1f} | "
            f"{row['latency_p95_ms']:.1f} | {row['peak_cuda_allocated_mb']:.1f} |"
        )
    lines.extend(
        [
            "",
            r"\* 幻觉字段率只统计通过严格 Schema 校验、被接受的预测；Schema 失败需结合合法率判断。",
            "",
            "| 训练方法 | 时长s | 训练峰值MiB | 初始验证loss | 最终验证loss | 可训练参数 | Adapter大小MiB |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name in ("lora", "qlora"):
        row = training[name]
        lines.append(
            f"| {name.upper()} | {row['duration_seconds']:.2f} | {row['peak_cuda_allocated_mb']:.1f} | "
            f"{row['initial_validation_loss']:.4f} | {row['final_validation_loss']:.4f} | "
            f"{row['trainable_parameters']} | {row['adapter_size_bytes'] / 1024 / 1024:.2f} |"
        )
    lines.extend(
        [
            "",
            "结论：本次合成集上 LoRA 质量最好。QLoRA 推理分配显存更低，但训练没有更省、推理也更慢；0.6B 模型不足以体现其面向大模型的主要价值。双待办样本暴露不同错误：LoRA 漏掉第二项，QLoRA 抽出两项却输出成两个相邻顶层数组，因而被严格 Schema 拒绝。",
            "",
            "Prompt-only 的幻觉字段率显示为 0 是因为没有任何输出通过严格 Schema，不能理解为没有幻觉。逐条输出见对应 JSON 报告。",
        ]
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
