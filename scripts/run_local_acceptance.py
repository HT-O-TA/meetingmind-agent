"""Run the lightweight HTTP and Worker demo using existing local services."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def local_stack(overrides=None, api_bootstrap=None):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    env = dict(
        os.environ,
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        EMBEDDING_MODEL_NAME="meetingmind-smoke-fallback",
        MILVUS_URI="",
        ENABLE_RERANK="false",
        HEALTH_CHECK_TIMEOUT_SECONDS="3",
        RATE_LIMIT_LOGIN_COUNT="100",
        RATE_LIMIT_REGISTER_COUNT="100",
    )
    env.update(overrides or {})
    children = []

    def launch(*args):
        children.append(subprocess.Popen(
            [sys.executable, *args],
            cwd=ROOT / "backend",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))

    try:
        if api_bootstrap:
            launch("-c", api_bootstrap, str(port))
        else:
            launch("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if children[0].poll() is not None:
                raise SystemExit("Backend failed during startup")
            try:
                with urlopen(f"{base_url}/ready", timeout=5) as response:
                    if b'"status":"ok"' in response.read():
                        break
            except (URLError, TimeoutError):
                pass
            time.sleep(0.25)
        else:
            raise SystemExit("Backend dependencies did not become ready")
        launch("-m", "app.workers.run")
        yield base_url
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the business acceptance report")
    args = parser.parse_args()
    stage = "stack_start"
    try:
        with local_stack() as base_url:
            stage = "business_flow"
            command = [sys.executable, str(ROOT / "scripts" / "demo_http_business_flow.py"),
                       "--base-url", base_url, "--timeout", "60", "--profile", "local-lightweight"]
            if args.output:
                command.extend(["--output", str(args.output.resolve())])
            result = subprocess.run(command, cwd=ROOT / "backend", check=False)
            if result.returncode:
                raise SystemExit(result.returncode)
            return 0
    except (OSError, RuntimeError, SystemExit) as exc:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({
                "schema_version": "meetingmind.http-flow.v1",
                "profile": "local-lightweight", "transport": "http", "status": "failed",
                "failed_stage": stage, "error_type": type(exc).__name__,
            }, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
