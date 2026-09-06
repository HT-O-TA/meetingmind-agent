"""MeetingMind 五分钟固定演示编排器。

覆盖：HTTP 正常链路/权限拒绝、工具确认门禁、队列失败恢复。
每次运行都会留下 manifest、标准输出和标准错误，方便复核而不是只看口头演示。
"""
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
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def run_step(name: str, command: list[str], cwd: Path, env: dict[str, str], output_dir: Path, timeout: float) -> dict:
    started = datetime.now(timezone.utc)
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        completed = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nstep timeout after {timeout}s\n",
        )
    ended = datetime.now(timezone.utc)
    (output_dir / f"{name}.stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (output_dir / f"{name}.stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    return {
        "name": name,
        "status": "timed_out" if timed_out else ("passed" if completed.returncode == 0 else "failed"),
        "returncode": completed.returncode,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": round((ended - started).total_seconds(), 3),
        "stdout_log": str(output_dir / f"{name}.stdout.log"),
        "stderr_log": str(output_dir / f"{name}.stderr.log"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 MeetingMind 五分钟固定演示")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="HTTP Demo 的服务地址")
    parser.add_argument("--http-timeout", type=float, default=90.0)
    parser.add_argument("--step-timeout", type=float, default=90.0, help="每个子演示的硬超时秒数")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "five-minute-demo")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    python = select_python(BACKEND / "venv" / "bin" / "python", BACKEND / ".venv" / "Scripts" / "python.exe", Path(sys.executable))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    env.setdefault("APP_ENV", "development")
    env.setdefault("MEETINGMIND_DEBUG", "false")
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:password@127.0.0.1:5432/meetingmind")
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    env.setdefault("RABBITMQ_URL", "amqp://admin:admin123@127.0.0.1:5672")

    commands = [
        (
            "01_http_business_flow",
            [str(python), str(REPO_ROOT / "scripts" / "demo_http_business_flow.py"), "--base-url", args.base_url, "--timeout", str(args.http_timeout), "--output", str(output_dir / "01_http_business_flow.json")],
        ),
        (
            "02_tool_confirmation",
            [str(python), str(BACKEND / "scripts" / "demo_tool_confirmation.py"), "--output", str(output_dir / "02_tool_confirmation.json")],
        ),
        (
            "03_queue_recovery",
            [str(python), str(BACKEND / "scripts" / "demo_queue_recovery.py"), "--output", str(output_dir / "03_queue_recovery.json")],
        ),
    ]
    results = []
    for name, command in commands:
        print(f"=== {name} ===", flush=True)
        results.append(run_step(name, command, REPO_ROOT, env, output_dir, args.step_timeout))

    passed = all(item["status"] == "passed" for item in results)
    manifest = {
        "schema_version": "meetingmind.five-minute-demo.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": ["normal_path", "permission_rejection", "tool_confirmation", "queue_recovery"],
        "results": results,
        "status": "passed" if passed else "incomplete",
        "limitations": [
            "HTTP 主链需要本地 API、PostgreSQL、Redis 和 RabbitMQ；服务未启动时会如实记录失败。",
            "工具确认步骤只验证策略门禁，不执行真实 Jira 外部写入。",
            "队列恢复使用确定性故障注入，不能替代生产多副本故障演练。",
            "总时长是否小于五分钟取决于本地服务和网络状态，manifest 会记录每一步耗时。",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={manifest_path} status={manifest['status']}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
