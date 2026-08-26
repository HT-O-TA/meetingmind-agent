# MeetingMind 轻量 Web/Worker 镜像。
# 本地 Transformer、FunASR 和微调环境属于独立模型能力，不打包进 Web 镜像。
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system meetingmind \
    && useradd --system --gid meetingmind --home-dir /app meetingmind \
    && mkdir -p /app/uploads /app/logs \
    && chown -R meetingmind:meetingmind /app

COPY requirements-runtime.txt requirements-runtime.lock ./
RUN pip install --no-cache-dir -r requirements-runtime.lock

COPY --chown=meetingmind:meetingmind app ./app

USER meetingmind

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
