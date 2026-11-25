"""Inject process failures only into the explicit isolated Compose project."""
import json
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from demo_http_business_flow import register_and_login, require, wait_for_task
from verify_replicas import ROOT, compose

WORKER = "meetingmind-replica-verify-crash-worker"
API_A = "http://127.0.0.1:18110"


def eventually(predicate, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(.25)
    raise RuntimeError("Fault fixture did not reach expected state")


def ready(client, url):
    try:
        return client.get(url + "/ready").status_code == 200
    except httpx.TransportError:
        return False


def verify():
    compose("stop", "worker-a", "worker-b")
    compose("run", "-d", "--rm", "--name", WORKER, "worker-a", "python", "/verify/replica_worker_fault_fixture.py")
    try:
        with httpx.Client(base_url=API_A, trust_env=False, timeout=22) as client:
            eventually(lambda: ready(client, API_A))
            name = "fault_" + uuid.uuid4().hex[:10]
            bearer = register_and_login(client, name, name + "@example.com", "Replica")
            headers = {"Authorization": "Bearer " + bearer}
            meeting = require(client.post("/api/v1/meetings", headers=headers,
                json={"title": name, "department": "Replica"}), 200)["data"]["id"]
            doc = require(client.post("/api/v1/documents/upload", headers=headers,
                data={"meeting_id": meeting}, files={"file": ("fault.txt", "Fault fixture document", "text/plain")}),
                200)["data"]
            task = require(client.post("/api/v1/tasks/documents", headers=headers,
                json={"document_id": doc["id"]}), 202)["task_id"]
            marker = eventually(lambda: re.search(
                rf"claimed-for-crash {re.escape(task)} child=([a-f0-9-]+)",
                subprocess.check_output(["docker", "logs", WORKER], stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace")))
            child_id = marker[1]
            broker = compose("exec", "-T", "rabbitmq", "rabbitmqctl", "-q", "list_queues",
                             "name", "messages_ready", "messages_unacknowledged")
            assert "document_process\t0\t1" in broker, broker
            killed_at = time.monotonic()
            subprocess.run(["docker", "kill", "--signal", "KILL", WORKER], check=True, capture_output=True)
            compose("start", "worker-b")
            final = wait_for_task(client, bearer, task, 60)
            assert final["status"] == "completed", final["status"]
            assert final["result"]["vector_task_id"] == child_id
            assert wait_for_task(client, bearer, child_id, 30)["status"] == "completed"
            after = compose("logs", "--no-color", "worker-b")
            deliveries = after.count(f"Received document task: {task}")
            assert deliveries >= 1
            worker = {"task_id": task, "unacked_before_kill": 1, "later_deliveries": deliveries,
                      "terminal": final["status"], "attempt_count": final.get("attempt_count"),
                      "original_vector_task_id": child_id, "same_vector_task_completed": True,
                      "seconds_after_kill": round(time.monotonic() - killed_at, 2)}

            def stream():
                try:
                    with client.stream("POST", "/api/v1/agents/query-stream", headers=headers,
                                       json={"question": "Summarize the fixture"}) as response:
                        body = response.read()
                        return response.status_code, b"[DONE]" in body
                except httpx.TransportError:
                    return "disconnected", False

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(stream)
                eventually(lambda: "meetingmind_http_in_flight_requests 1.0" in client.get("/metrics").text)
                compose("kill", "-s", "KILL", "api-a")
                assert first.result(timeout=10) == ("disconnected", False)
                peer_ok = ready(client, "http://127.0.0.1:18111")
                compose("start", "api-a")
                eventually(lambda: ready(client, API_A))
                assert "meetingmind_http_in_flight_requests 0.0" in client.get("/metrics").text
                assert pool.submit(stream).result(timeout=22) == (200, True)
                assert peer_ok
            return {"worker": worker, "sse": {"old_stream": "disconnected", "fresh_in_flight": 0,
                                              "new_stream_completed": True, "peer_ready": peer_ok}}
    finally:
        subprocess.run(["docker", "stop", WORKER], capture_output=True)
        compose("start", "api-a", "worker-a", "worker-b")


if __name__ == "__main__":
    result = json.dumps(verify(), indent=2)
    (ROOT / "artifacts/replica-process-fault-recovery.json").write_text(result + "\n", encoding="utf-8")
    print(result)
