"""Compose 部署前置检查；报告只记录是否存在密钥，不输出密钥值。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Mapping


PRODUCTION_REQUIRED = (
    "DATABASE_URL",
    "RABBITMQ_USER",
    "RABBITMQ_PASSWORD",
    "SECRET_KEY",
    "CORS_ORIGINS",
)
INSECURE_VALUES = {
    "password",
    "admin",
    "admin123",
    "your-secret-key-here-change-in-production",
    "meetingmind-dev-only-secret-change-before-production",
}


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number} 不是 KEY=VALUE")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def validate_production(values: Mapping[str, str]) -> list[str]:
    errors = [f"missing production variable: {name}" for name in PRODUCTION_REQUIRED if not values.get(name)]
    for name in ("RABBITMQ_PASSWORD", "SECRET_KEY"):
        value = values.get(name, "")
        if value and (value in INSECURE_VALUES or len(value) < 16):
            errors.append(f"{name} is an example/weak value")
    if values.get("SECRET_KEY") and len(values["SECRET_KEY"]) < 32:
        errors.append("SECRET_KEY must contain at least 32 characters")
    cors = values.get("CORS_ORIGINS", "")
    if "*" in cors or "localhost" in cors or "127.0.0.1" in cors:
        errors.append("production CORS_ORIGINS must not use wildcard or localhost")
    return errors


def compose_command() -> list[str] | None:
    standalone = shutil.which("docker-compose")
    if standalone:
        return [standalone]
    docker = shutil.which("docker")
    if docker:
        result = subprocess.run([docker, "compose", "version"], capture_output=True, text=True)
        if result.returncode == 0:
            return [docker, "compose"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("development", "production"), default="development")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        file_values = read_env_file(args.env_file)
    except ValueError as exc:
        file_values = {}
        errors.append(str(exc))
    values = {**file_values, **os.environ}
    if args.mode == "production":
        errors.extend(validate_production(values))

    compose = compose_command()
    docker = shutil.which("docker")
    checks = {
        "docker_cli_found": bool(docker),
        "compose_cli_found": bool(compose),
        "docker_daemon_reachable": False,
        "compose_config_valid": False,
        "env_file_present": args.env_file.exists(),
    }
    versions: dict[str, str] = {}
    if docker:
        daemon = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
        )
        checks["docker_daemon_reachable"] = daemon.returncode == 0
        if daemon.returncode == 0:
            versions["docker_server"] = daemon.stdout.strip()
        else:
            errors.append("Docker daemon is not reachable")
    else:
        errors.append("docker CLI is missing")

    if compose:
        version = subprocess.run([*compose, "version"], capture_output=True, text=True)
        versions["compose"] = (version.stdout or version.stderr).strip().splitlines()[0]
        config_files = ["-f", "docker-compose.yml"]
        if args.mode == "production":
            config_files.extend(["-f", "docker-compose.prod.yml"])
        configured = subprocess.run(
            [*compose, *config_files, "config", "--quiet"],
            capture_output=True,
            text=True,
            env=values,
        )
        checks["compose_config_valid"] = configured.returncode == 0
        if configured.returncode:
            errors.append("Compose config is invalid: " + (configured.stderr.strip() or "unknown error"))
    else:
        errors.append("Docker Compose CLI is missing")

    report = {
        "schema_version": "meetingmind.deploy-preflight.v1",
        "mode": args.mode,
        "status": "passed" if not errors else "failed",
        "checks": checks,
        "versions": versions,
        "production_required_presence": {
            name: bool(values.get(name)) for name in PRODUCTION_REQUIRED
        },
        "errors": errors,
        "notes": [
            "密钥值不会写入报告。",
            "通过 preflight 只证明本机配置可启动，不代表 TLS、备份、高可用或容量验收。",
        ],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
