#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

if [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

# 隔离宿主机 ROS 等第三方 pytest 插件，并固定生产 Router 边界。
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export APP_ENV=production
export DEBUG=false
export SECRET_KEY="${SECRET_KEY:-meetingmind-core-test-secret-at-least-32-characters}"

exec "$PYTHON_BIN" -m pytest -p pytest_asyncio.plugin "$@"
