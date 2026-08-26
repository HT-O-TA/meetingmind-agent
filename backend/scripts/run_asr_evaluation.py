"""下载清单中的公开样例，运行真实 FunASR 并生成 CER/WER 报告。"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from app.evaluation.asr_metrics import character_error_rate, word_error_rate
from app.services.asr_service import FunASRService


def load_manifest(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        required = {"id", "source_url", "reference", "language", "sample_kind"}
        missing = required - row.keys()
        if missing:
            raise ValueError(f"manifest line {line_number} missing: {sorted(missing)}")
        if urlparse(row["source_url"]).scheme != "https":
            raise ValueError("ASR evaluation only downloads HTTPS sources")
        rows.append(row)
    if not rows:
        raise ValueError("ASR manifest is empty")
    return rows


def download(row: dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / f"{row['id']}.wav"
    if destination.exists():
        return destination
    with urlopen(row["source_url"], timeout=60) as response:
        content = response.read()
    destination.write_bytes(content)
    return destination


async def evaluate(manifest: Path, cache_dir: Path) -> dict:
    service = FunASRService()
    samples = []
    for row in load_manifest(manifest):
        audio_path = download(row, cache_dir)
        cold_result = await service.transcribe(audio_path)
        result = await service.transcribe(audio_path)
        samples.append({
            **row,
            "hypothesis": result.text,
            "cer": round(character_error_rate(row["reference"], result.text), 6),
            "wer_jieba": round(word_error_rate(row["reference"], result.text, row["language"]), 6),
            "audio_sha256": result.audio_sha256,
            "duration_seconds": result.duration_seconds,
            "cold_start_latency_seconds": cold_result.latency_seconds,
            "cold_model_load_seconds": cold_result.initialization_seconds,
            "latency_seconds": result.latency_seconds,
            "model_load_seconds": result.initialization_seconds,
            "inference_seconds": result.inference_seconds,
            "realtime_factor": result.realtime_factor,
            "segment_count": len(result.segments),
            "speaker_count": len(result.speakers),
            "timestamp_source": result.timestamp_source,
            "diarization_available": result.diarization_available,
            "uncertainties": result.uncertainties,
            "cold_and_warm_hypotheses_match": cold_result.text == result.text,
        })
    sample_count = len(samples)
    real_count = sum(sample["sample_kind"] == "real_meeting" for sample in samples)
    first = samples[0]
    return {
        "schema_version": "meetingmind.asr-eval.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest),
        "model": {
            "provider": "funasr",
            "configured_model": __import__("app.core.config", fromlist=["settings"]).settings.ASR_MODEL,
            "package_version": __import__("importlib.metadata", fromlist=["version"]).version("funasr"),
            "device": service._device,
        },
        "metrics": {
            "sample_count": sample_count,
            "real_meeting_sample_count": real_count,
            "macro_cer": round(sum(item["cer"] for item in samples) / sample_count, 6),
            "macro_wer_jieba": round(sum(item["wer_jieba"] for item in samples) / sample_count, 6),
        },
        "claim_status": (
            "meeting_domain_baseline" if real_count == sample_count else "public_smoke_only"
        ),
        "limitations": [
            "公开单句样例只证明真实模型和评测链路可运行，不能代表会议领域质量。",
            "中文 WER 使用 jieba 分词，必须与该归一化规则一起解读；CER 是主要指标。",
            "没有带真值的多人会议样本，因此不报告 DER 或说话人准确率。",
            "每条样例连续执行两次：第一次记录缓存模型的进程冷启动，第二次记录热推理。",
        ],
        "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evaluation/datasets/asr_public_smoke.jsonl"),
    )
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/asr-eval"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.manifest, args.cache_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    print(f"claim_status={report['claim_status']} output={args.output}")


if __name__ == "__main__":
    main()
