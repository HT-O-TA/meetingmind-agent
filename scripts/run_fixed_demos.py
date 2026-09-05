"""按固定输入依次运行 HTTP 主链、队列、ASR、LoRA 四个求职 Demo。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"


def select_python(*candidates: Path) -> Path:
    """优先使用项目虚拟环境；在 Windows/Linux 都能找到正确解释器。"""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def run_step(name: str, command: list[str], cwd: Path, env: dict[str, str]) -> dict:
    print(f"\n=== {name} ===", flush=True)
    started = datetime.now(timezone.utc)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    ended = datetime.now(timezone.utc)
    return {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": round((ended - started).total_seconds(), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo",
        action="append",
        choices=("http", "queue", "asr", "lora"),
        help="可重复传入；默认运行全部四个固定 Demo。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "fixed-demos",
    )
    args = parser.parse_args()
    selected = args.demo or ["http", "queue", "asr", "lora"]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_env = os.environ.copy()
    runtime_env["APP_ENV"] = "development"
    runtime_env["DEBUG"] = "false"
    runtime_env["ENABLE_ASR"] = "true"
    runtime_env["ASR_MODEL"] = "paraformer-zh"
    runtime_env["ASR_VAD_MODEL"] = "fsmn-vad"
    runtime_env["ASR_PUNC_MODEL"] = "ct-punc"
    runtime_env["ASR_SPK_MODEL"] = "cam++"
    runtime_env["ASR_DEVICE"] = "auto"
    runtime_env["PYTHONPATH"] = str(BACKEND)
    runtime_env.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://postgres:password@127.0.0.1:5432/meetingmind"
    )
    runtime_env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    runtime_env.setdefault("RABBITMQ_URL", "amqp://admin:admin123@127.0.0.1:5672")
    core_python = select_python(
        BACKEND / "venv" / "bin" / "python",
        BACKEND / "venv" / "Scripts" / "python.exe",
        BACKEND / ".venv" / "bin" / "python",
        BACKEND / ".venv" / "Scripts" / "python.exe",
    )
    asr_python = select_python(
        BACKEND / ".venv-asr" / "bin" / "python",
        BACKEND / ".venv-asr" / "Scripts" / "python.exe",
        core_python,
    )
    finetune_python = select_python(
        BACKEND / ".venv-ft" / "bin" / "python",
        BACKEND / ".venv-ft" / "Scripts" / "python.exe",
        core_python,
    )
    commands = {
        "http": [
            str(core_python),
            str(REPO_ROOT / "scripts" / "demo_http_business_flow.py"),
            "--output",
            str(output_dir / "00_http_business_flow.json"),
        ],
        "queue": [
            str(core_python),
            "scripts/demo_queue_recovery.py",
            "--output",
            str(output_dir / "01_queue_recovery.json"),
        ],
        "asr": [
            str(asr_python),
            "scripts/run_asr_queue_smoke.py",
            "--audio",
            ".cache/asr-eval/funasr_aishell_BAC009S0764W0121.wav",
            "--output",
            str(output_dir / "02_asr_evidence.json"),
        ],
        "lora": [
            str(finetune_python),
            "finetuning/infer_todos.py",
            "--text",
            "[00:08.00] 成员乙: 请成员丙在周五前整理发布核对表。",
            "--source-id",
            "fixed-demo-stage6-001",
            "--protocol",
            "lora",
            "--base-model",
            "model/qwen3-0.6B",
            "--adapter",
            "finetuning/artifacts/qwen3-0.6b-todo-lora",
            "--output",
            str(output_dir / "03_lora_extraction.json"),
        ],
    }

    results = []
    for name in selected:
        command = commands[name]
        results.append(run_step(name, command, BACKEND, runtime_env))

    manifest = {
        "schema_version": "meetingmind.fixed-demos.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected": selected,
        "results": results,
        "status": "passed" if results and all(r["status"] == "passed" for r in results) else "incomplete",
        "limitations": [
            "输出目录默认被 Git 忽略；正式证据只提交去敏报告与固定命令。",
            "HTTP 主链 Demo 会在本地开发数据库保留随机后缀的演示用户与业务记录。",
            "ASR 输入是公开单句，不是多人会议真值。",
            "LoRA 输入与训练数据均为项目自编合成样例。",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nmanifest={manifest_path} status={manifest['status']}")
    return 0 if manifest["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
