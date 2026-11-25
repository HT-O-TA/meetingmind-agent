"""Short, local-only concurrency baseline against HTTP and a real Worker."""

import argparse
import json
import math
import os
import platform
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from demo_http_business_flow import register_and_login, require, wait_for_task
from run_local_acceptance import local_stack


BOOTSTRAP = """
import asyncio, importlib, sys, uvicorn
from types import SimpleNamespace
from app.core.cache_init import get_cache_stats
from app.services.vector_cache_manager import get_cache_manager
from app.main import app

@app.get("/_bench/cache", include_in_schema=False)
async def cache_metrics():
    counters = get_cache_stats()
    return {
        **{kind: {metric: counters[f"{kind}_cache_{metric}"] for metric in ("hits", "misses")}
           for kind in ("api", "llm")},
        "retrieval": get_cache_manager().get_cache_stats()["retrieval"],
    }
agents = importlib.import_module("app.api.v1.endpoints.agents")
async def query(*args, **kwargs):
    await asyncio.sleep(0.25)
    return SimpleNamespace(
        success=True, answer="synthetic capacity fixture", citations=[], error=None,
        task_type=None, workflow_type=None, risk_level=None, route_reason=None,
        retrieval_confidence=None, plan_confidence=None, uncertainty_flags=[],
        validation_errors=[], policy_results=[], requires_confirmation=False,
        confirmation_status=None, pending_action=None, minutes=None, todos=[],
        controversies=[], plan=None, budget_ledger={}, context_manifest={},
        structured_outputs={}, metadata={}, route_decision=None,
    )
async def agent(*args, **kwargs):
    return SimpleNamespace(process_query_with_context=query)
agents.get_agent_service = agent
uvicorn.run("app.main:app", host="127.0.0.1", port=int(sys.argv[1]))
"""

SETTINGS = {
    "RATE_LIMIT_RAG_COUNT": "500", "RATE_LIMIT_AGENT_COUNT": "500",
    "RATE_LIMIT_AGENT_STREAM_COUNT": "500", "RATE_LIMIT_TASK_COUNT": "500",
    "AGENT_HTTP_MAX_IN_FLIGHT": "8",
}


def percentile(values, fraction):
    if values:
        return round(sorted(values)[math.ceil(len(values) * fraction) - 1], 2)
    return None


def timed(action, index):
    started = time.perf_counter()
    try:
        item = action(index)
    except Exception as exc:
        item = {"outcome": "unexpected_error", "error_type": type(exc).__name__}
    ended = time.perf_counter()
    return {**item, "elapsed_ms": (ended - started) * 1000, "ended": ended}


def run_level(action, concurrency, requests, seconds=0):
    start = time.perf_counter()
    deadline = start + seconds
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = []
        while True:
            rows.extend(pool.map(lambda index: timed(action, index), range(len(rows), len(rows) + requests)))
            if not seconds or time.perf_counter() >= deadline or any(
                row["outcome"] == "unexpected_error" for row in rows
            ):
                break
    wall = time.perf_counter() - start
    requests = len(rows)
    outcomes = {key: sum(row["outcome"] == key for row in rows)
                for key in ("ok", "rate_limited", "capacity_rejected", "unexpected_error")}
    successful = [row for row in rows if row["outcome"] == "ok"]
    result = {
        "concurrency": concurrency, "requests": requests, "wall_seconds": round(wall, 2), **outcomes,
        "unexpected_error_rate": outcomes["unexpected_error"] / requests,
        "successful_per_second": round(len(successful) / wall, 2),
    }
    for label in ("elapsed_ms", "first_event_ms", "upload_ms", "enqueue_ms", "task_ms"):
        values = [row[label] for row in successful if label in row]
        if values:
            result[label] = {"p50": percentile(values, .5), "p95": percentile(values, .95)}
    if any("accepted" in row for row in rows):
        points = sorted((point, delta) for row in rows if "accepted" in row
                        for point, delta in ((row["accepted"], 1), (row["ended"], -1)))
        active = peak = 0
        for _, delta in points:
            active += delta
            peak = max(peak, active)
        result["observed_outstanding_peak"] = peak
        result["drain_after_last_admission_ms"] = round(
            max(0, points[-1][0] - max(row["accepted"] for row in rows if "accepted" in row)) * 1000, 2
        )
    if any("cited" in row for row in successful):
        result["citation_return_rate"] = sum(row.get("cited", False) for row in successful) / len(successful)
    result["error_types"] = sorted({row["error_type"] for row in rows if "error_type" in row})
    return result


def classify(response):
    if response.status_code == 429:
        return {"outcome": "rate_limited"}
    if response.status_code == 503 and response.headers.get("Retry-After") == "1":
        return {"outcome": "capacity_rejected"}
    return {"outcome": "unexpected_error", "error_type": f"HTTP_{response.status_code}"}


def benchmark(base_url, args, verify=True):
    with httpx.Client(base_url=base_url, timeout=15, trust_env=False, verify=verify) as client:
        accounts = []
        for _ in range(args.users):
            user = "bench_" + uuid.uuid4().hex[:12]
            bearer = register_and_login(client, user, user + "@example.com", "Bench")
            headers = {"Authorization": "Bearer " + bearer}
            meeting = require(client.post("/api/v1/meetings", headers=headers, json={
                "title": user, "department": "Bench",
            }), 200)["data"]["id"]
            accounts.append((bearer, headers, meeting))

        def account(index):
            return accounts[index % len(accounts)]

        def upload(index):
            _, headers, meeting = account(index)
            return client.post("/api/v1/documents/upload", headers=headers, data={"meeting_id": str(meeting)},
                               files={"file": ("bench.txt", "Release checks are due on Friday. \u4f1a\u8bae \u9879\u76ee \u6d4b\u8bd5 \u90e8\u7f72.", "text/plain")})

        def rag(index, question="release checks"):
            _, headers, meeting = account(index)
            res = client.post("/api/v1/rag/ask", headers=headers, json={
                "question": question, "meeting_id": meeting, "top_k": 5, "use_llm": False,
            })
            if res.status_code != 200:
                return classify(res)
            return {"outcome": "ok", "cited": bool(res.json()["data"]["citations"])}

        def agent(index):
            _, headers, _ = account(index)
            res = client.post("/api/v1/agents/query", headers=headers, json={"question": "Summarize release checks."})
            if res.status_code != 200:
                return classify(res)
            return {"outcome": "ok" if res.json()["success"] else "unexpected_error"}

        def stream(index):
            start = time.perf_counter()
            _, headers, _ = account(index)
            with client.stream("POST", "/api/v1/agents/query-stream", headers=headers,
                               json={"question": "Summarize release checks."}) as res:
                if res.status_code != 200:
                    return classify(res)
                first = None
                completed = False
                for line in res.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    if first is None:
                        first = (time.perf_counter() - start) * 1000
                    if line == "data: [DONE]":
                        return {"outcome": "ok" if completed else "unexpected_error", "first_event_ms": first}
                    item = json.loads(line[6:])
                    if item.get("type") == "final":
                        completed = item["data"]["success"] is True
            return {"outcome": "unexpected_error", "error_type": "missing_done"}

        def task(index):
            start = time.perf_counter()
            token, headers, _ = account(index)
            res = upload(index)
            after_upload = time.perf_counter()
            if res.status_code != 200:
                return classify(res)
            res = client.post("/api/v1/tasks/documents", headers=headers, json={"document_id": res.json()["data"]["id"]})
            accepted = time.perf_counter()
            if res.status_code != 202:
                return classify(res)
            parent = wait_for_task(client, token, res.json()["task_id"], 30)
            if parent["status"] != "completed":
                return {"outcome": "unexpected_error", "error_type": parent["status"], "accepted": accepted}
            child = wait_for_task(client, token, parent["result"]["vector_task_id"], 30)
            return {"outcome": "ok" if child["status"] == "completed" else "unexpected_error",
                    "accepted": accepted, "upload_ms": (after_upload-start)*1000,
                    "enqueue_ms": (accepted-after_upload)*1000, "task_ms": (time.perf_counter()-accepted)*1000}

        for index in range(len(accounts)):
            seeded = task(index)
            if seeded["outcome"] != "ok":
                raise RuntimeError(f"Indexing benchmark seed document failed: {seeded}")
        results = {}
        for name, action in (("rag", rag), ("agent", agent), ("sse", stream), ("upload_queue", task)):
            levels = results[name] = []
            for concurrency in args.concurrency:
                warmup = getattr(args, "warmup", 0)
                if warmup:
                    warmed = run_level(action, concurrency, warmup)
                    if warmed["unexpected_error"] or warmed["rate_limited"]:
                        raise RuntimeError(f"{name} warmup failed: {warmed}")
                level = run_level(action, concurrency, args.requests, getattr(args, "seconds", 0))
                level["warmup_requests"] = warmup
                levels.append(level)
                print(name, concurrency, "ok", level["ok"], "errors", level["unexpected_error"], flush=True)
                if level["unexpected_error"]:
                    break
        if getattr(args, "mixed_cache", False):
            before = require(client.get("/_bench/cache"), 200)
            # 70 distinct scoped keys, then replay 30 of those exact requests.
            rows = [rag(index, f"\u4f1a\u8bae \u9879\u76ee \u6d4b\u8bd5 {index}")
                    for index in (*range(70), *range(30))]
            after = require(client.get("/_bench/cache"), 200)
            counters = {
                kind: {metric: after[kind][metric] - before[kind][metric]
                       for metric in ("hits", "misses")}
                for kind in after
            }
            results["mixed_cache"] = {
                "requests": len(rows), "repeated_requests": 30,
                "outcomes": {key: sum(row["outcome"] == key for row in rows)
                             for key in ("ok", "rate_limited", "capacity_rejected", "unexpected_error")},
                "counters": counters,
            }
        results["capacity_recovery"] = {"agent": agent(0)["outcome"], "sse": stream(0)["outcome"]}
        return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4, 8, 16])
    parser.add_argument("--requests", type=int, default=16)
    parser.add_argument("--warmup", type=int, choices=range(33), default=0)
    parser.add_argument("--mixed-cache", action="store_true")
    parser.add_argument("--users", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.requests <= 100 or any(not 1 <= c <= 16 for c in args.concurrency):
        parser.error("local safety bounds: 1–100 requests per level and concurrency 1–16")
    with local_stack(SETTINGS, BOOTSTRAP) as base_url:
        results = benchmark(base_url, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "mode": "local-lightweight", "agent_backend": "synthetic 250 ms service",
        "users": args.users,
        "host": {"os": platform.system(), "logical_cpus": os.cpu_count(),
                 "python": platform.python_version()},
        "queue_peak": "client-observed accepted jobs not yet terminal; not broker depth",
        "transport": "loopback HTTP", "api_instances": 1, "worker_instances": 1,
        "retrieval": {"milvus": False, "rerank": False, "generation": False,
                      "embedding": "local term-frequency fallback"},
        "settings": SETTINGS, "results": results,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
