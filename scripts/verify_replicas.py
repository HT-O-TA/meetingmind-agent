"""Verify shared admission, independent streaming slots, and actual queue delivery."""
import json
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from demo_http_business_flow import register_and_login, require, wait_for_task

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.replica-verify.yml")]


def compose(*args):
    return subprocess.check_output([*COMPOSE, *args], text=True, encoding="utf-8", errors="replace")


def verify():
    urls = [f"http://127.0.0.1:{port}" for port in (18110, 18111)]
    with httpx.Client(trust_env=False, timeout=25) as client:
        until = time.monotonic() + 40
        for url in urls:
            while True:
                try:
                    if client.get(url + "/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > until:
                    raise RuntimeError(f"API did not become ready: {url}")
                time.sleep(.3)
        with httpx.Client(base_url=urls[0], trust_env=False) as api:
            user = "replica_" + uuid.uuid4().hex[:10]
            bearer = register_and_login(api, user, user + "@example.com", "Replica")
            headers = {"Authorization": "Bearer " + bearer}
            meeting = require(api.post("/api/v1/meetings", headers=headers, json={
                "title": user, "department": "Replica",
            }), 200)["data"]["id"]
            statuses = [client.post(urls[i] + "/api/v1/rag/ask", headers=headers, json={
                "meeting_id": meeting, "question": "deployment status", "use_llm": False,
            }).status_code for i in (0, 1, 0)]
            assert statuses == [200, 200, 429], statuses
            task_ids = []
            for index in range(6):
                doc = require(api.post("/api/v1/documents/upload", headers=headers,
                    data={"meeting_id": meeting},
                    files={"file": (f"replica-{index}.txt", "Deployment task fixture", "text/plain")}), 200)["data"]
                task_ids.append(require(api.post("/api/v1/tasks/documents", headers=headers,
                    json={"document_id": doc["id"]}), 202)["task_id"])
            for task_id in task_ids:
                assert wait_for_task(api, bearer, task_id, 30)["status"] == "completed", task_id
            deliveries = {}
            for worker in ("worker-a", "worker-b"):
                log = compose("logs", "--no-color", worker)
                deliveries[worker] = [task_id for task_id in re.findall(r"Received document task: ([a-f0-9-]+)", log)
                                      if task_id in task_ids]
            observed = deliveries["worker-a"] + deliveries["worker-b"]
            assert all(deliveries.values()) and sorted(observed) == sorted(task_ids), deliveries

        def stream(url):
            with client.stream("POST", url + "/api/v1/agents/query-stream", headers=headers,
                               json={"question": "Summarize the deployment meeting"}) as response:
                response.read()
                return response.status_code, "[DONE]" in response.text

        def scrape(url):
            response = client.get(url + "/metrics")
            response.raise_for_status()
            return response.text

        with ThreadPoolExecutor(max_workers=18) as pool:
            streams = [pool.submit(stream, url) for url in urls for _ in range(8)]
            peak = []
            for _ in range(30):
                peak = [float(re.search(r"(?m)^meetingmind_http_in_flight_requests ([\d.]+)$", scrape(url))[1])
                        for url in urls]
                if peak == [8, 8]:
                    break
                time.sleep(.2)
            assert peak == [8, 8], peak
            rejected = list(pool.map(stream, urls))
            assert rejected == [(503, False)] * 2, rejected
            assert all(f.result() == (200, True) for f in streams)
        scrapes = [scrape(url) for url in urls]
        assert all("meetingmind_http_duration_seconds_bucket" in s and 'status="503"' in s for s in scrapes)
        assert 'status="429"' in scrapes[0]
        for suffix, content in zip(("a", "b"), scrapes):
            (ROOT / f"artifacts/replica-metrics-{suffix}.prom").write_text(content, encoding="utf-8")
        return {"status": "passed", "shared_rate_limit": statuses, "deliveries": deliveries,
                "sse_active": peak, "sse_over_limit": [r[0] for r in rejected],
                "tasks_completed": len(task_ids)}


if __name__ == "__main__":
    result = json.dumps(verify(), indent=2)
    (ROOT / "artifacts/replica-verify.json").write_text(result + "\n", encoding="utf-8")
    print(result)
