"""Compose健康探针与日志容量边界契约。"""

from pathlib import Path


COMPOSE_PATH = Path(__file__).resolve().parents[3] / "docker-compose.yml"


def test_all_services_use_the_shared_bounded_local_log_policy():
    text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "x-service-logging: &service-logging" in text
    assert "driver: local" in text
    assert "max-size: ${DOCKER_LOG_MAX_SIZE:-10m}" in text
    assert "max-file: ${DOCKER_LOG_MAX_FILES:-3}" in text
    assert text.count("logging: *service-logging") == 5


def test_backend_container_healthcheck_uses_readiness():
    text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "http://127.0.0.1:8000/ready" in text
    assert "http://127.0.0.1:8000/health" not in text
