#!/usr/bin/env bash
# 在 WSL 里启动本地 vLLM（OpenAI 兼容，端口 8000），供 bench_vllm_serving.py 压测。
# 用法：bash serve_vllm_wsl.sh [gpu_memory_utilization] [max_model_len]
set -euo pipefail
VENV="${VLLM_VENV:-$HOME/vllm010}"          # vllm==0.10.0 + torch 2.7.1+cu126 + transformers==4.53.2
MODEL="${VLLM_MODEL_PATH:-/mnt/f/project/meetingmind-agent/model/Qwen3-1.7B}"
exec "$VENV/bin/vllm" serve "$MODEL" --served-model-name qwen3-1.7b \
  --host 0.0.0.0 --port 8000 --dtype float16 \
  --gpu-memory-utilization "${1:-0.75}" --max-model-len "${2:-2048}"
