"""通过真实 HTTP、PostgreSQL、Redis、RabbitMQ 和 Worker 验证核心业务闭环。"""
from __future__ import annotations

import argparse
import json
import secrets
import time
import uuid
from pathlib import Path

import httpx


TERMINAL_TASK_STATES = {
    "completed",
    "failed",
    "cancelled",
    "dead_letter",
    "publish_failed",
}


def require(response: httpx.Response, expected: int | tuple[int, ...]) -> dict:
    allowed = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in allowed:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:500]}"
        )
    return response.json()


def register_and_login(
    client: httpx.Client,
    username: str,
    email: str,
    department: str,
) -> str:
    password = secrets.token_urlsafe(24)
    require(
        client.post(
            "/api/v1/users/register",
            json={
                "username": username,
                "email": email,
                "password": password,
                "full_name": username,
                "department": department,
            },
        ),
        200,
    )
    payload = require(
        client.post(
            "/api/v1/users/login",
            json={"username": username, "password": password},
        ),
        200,
    )
    return payload["data"]["access_token"]


def wait_for_task(
    client: httpx.Client,
    token: str,
    task_id: str,
    timeout_seconds: float,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < deadline:
        task = require(client.get(f"/api/v1/tasks/{task_id}", headers=headers), 200)
        if task["status"] in TERMINAL_TASK_STATES:
            return task
        time.sleep(0.25)
    raise TimeoutError(f"task {task_id} did not finish within {timeout_seconds}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    suffix = uuid.uuid4().hex[:10]
    owner_name = f"flow_owner_{suffix}"
    outsider_name = f"flow_out_{suffix}"
    report: dict = {"schema_version": "meetingmind.http-flow.v1", "run_id": suffix}

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        require(client.get("/health"), 200)
        owner_token = register_and_login(
            client, owner_name, f"{owner_name}@example.com", "工程部"
        )
        outsider_token = register_and_login(
            client, outsider_name, f"{outsider_name}@example.com", "销售部"
        )
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

        meeting = require(
            client.post(
                "/api/v1/meetings",
                headers=owner_headers,
                json={
                    "title": f"真实演示会议 {suffix}",
                    "description": "验证鉴权、检索与异步任务闭环",
                    "department": "工程部",
                },
            ),
            200,
        )["data"]
        meeting_id = meeting["id"]

        document = require(
            client.post(
                "/api/v1/documents/upload",
                headers=owner_headers,
                data={"meeting_id": str(meeting_id), "department": "工程部"},
                files={
                    "file": (
                        f"demo-{suffix}.txt",
                        "项目决定周五发布。李雷负责发布检查，韩梅梅负责回归测试。",
                        "text/plain",
                    )
                },
            ),
            200,
        )["data"]
        document_id = document["id"]

        rag = require(
            client.post(
                "/api/v1/rag/ask",
                headers=owner_headers,
                json={
                    "question": "谁负责发布检查？",
                    "meeting_id": meeting_id,
                    "top_k": 3,
                    "use_llm": False,
                },
            ),
            200,
        )["data"]
        if rag["count"] < 1 or not rag["citations"]:
            raise AssertionError(f"RAG did not return evidence: {rag}")

        todo = require(
            client.post(
                "/api/v1/todos",
                headers=owner_headers,
                json={
                    "meeting_id": meeting_id,
                    "title": "执行发布检查",
                    "assignee_name": "李雷",
                    "priority": "high",
                },
            ),
            200,
        )["data"]

        parent = require(
            client.post(
                "/api/v1/tasks/documents",
                headers={
                    **owner_headers,
                    "Idempotency-Key": f"http-flow-{document_id}",
                },
                json={"document_id": document_id, "metadata": {"source": "http-demo"}},
            ),
            202,
        )
        parent = wait_for_task(client, owner_token, parent["task_id"], args.timeout)
        if parent["status"] != "completed":
            raise AssertionError(f"document task failed: {parent}")
        child_id = (parent.get("result") or {}).get("vector_task_id")
        if not child_id:
            raise AssertionError(f"document task did not create vector child: {parent}")
        child = wait_for_task(client, owner_token, child_id, args.timeout)
        if child["status"] != "completed":
            raise AssertionError(f"vector task failed: {child}")

        private_document_status = client.get(
            f"/api/v1/documents/{document_id}", headers=outsider_headers
        ).status_code
        cross_department_meeting_status = client.get(
            f"/api/v1/meetings/{meeting_id}", headers=outsider_headers
        ).status_code
        outsider_documents = require(
            client.get("/api/v1/documents", headers=outsider_headers), 200
        )["data"]
        if private_document_status != 403:
            raise AssertionError("private document access was not denied")
        if cross_department_meeting_status != 403:
            raise AssertionError("cross-department meeting access was not denied")
        if document_id in {item["id"] for item in outsider_documents}:
            raise AssertionError("private document leaked through list endpoint")

        report.update(
            {
                "status": "passed",
                "meeting_id": meeting_id,
                "document_id": document_id,
                "document_status": document["status"],
                "todo_id": todo["id"],
                "rag": {
                    "mode": rag["mode"],
                    "count": rag["count"],
                    "citation_count": len(rag["citations"]),
                    "answer_excerpt": rag["answer"][:120],
                },
                "queue": {
                    "document_task": parent["status"],
                    "vector_task": child["status"],
                    "embedded_chunks": child["result"]["embedded_chunks"],
                },
                "authorization": {
                    "private_document_status": private_document_status,
                    "cross_department_meeting_status": cross_department_meeting_status,
                    "private_document_hidden_from_list": True,
                },
            }
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
