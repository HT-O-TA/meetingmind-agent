#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  :  # 显式指定解释器（如 conda 环境）时优先使用
elif [[ -x "venv/bin/python" ]]; then
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
# 语义路由依赖本地 bge-m3，单测用假编码器单独覆盖，避免全量测试加载模型。
export ROUTE_SEMANTIC_TASK_ENABLED=false
# 测试与私有 backend/.env 隔离：固定默认模型与 provider，环境变量优先于 .env。
export LLM_PROVIDER=openai LLM_MODEL=qwen3.7-flash MODEL_TURBO_NAME=qwen3.7-flash MODEL_PLUS_NAME=qwen3.7-flash MODEL_MAX_NAME=qwen3.7-flash LLM_API_KEY= LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
export CORS_ORIGINS='["https://tests.invalid"]'

exec "$PYTHON_BIN" -m pytest -p pytest_asyncio.plugin "$@"
