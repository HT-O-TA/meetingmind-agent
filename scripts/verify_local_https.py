"""Run the local business acceptance through Nginx with verified HTTPS."""

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx

from run_local_acceptance import ROOT, local_stack
from bench_local_business import BOOTSTRAP, SETTINGS, benchmark


def cache_delta(before, after):
    result = {}
    for kind in ("api", "llm", "retrieval"):
        hits = after[kind]["hits"] - before[kind]["hits"]
        misses = after[kind]["misses"] - before[kind]["misses"]
        result[kind] = {"hits": hits, "misses": misses,
                        "hit_rate": hits / (hits + misses) if hits + misses else None}
    return result


LOAD_BOOTSTRAP = BOOTSTRAP.replace('uvicorn.run("app.main:app"', '''
from app.main import app
from app.core.cache_init import get_cache_stats
from app.services.vector_cache_manager import get_cache_manager
@app.get("/api/_acceptance/cache")
async def cache_counters():
    counters = get_cache_stats()
    return {
        **{kind: {"hits": counters[kind + "_cache_hits"], "misses": counters[kind + "_cache_misses"]}
           for kind in ("api", "llm")},
        "retrieval": get_cache_manager().get_cache_stats()["retrieval"],
    }
uvicorn.run("app.main:app"''')


@contextmanager
def https_edge(upstream, *, name=None):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        edge_port = sock.getsockname()[1]
    name = name or "meetingmind-https-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts", prefix="tls-") as folder:
        folder = Path(folder)
        cert = folder / "cert.pem"
        key = folder / "key.pem"
        subprocess.run(
            ["openssl", "req", "-config", os.devnull, "-x509", "-newkey", "rsa:2048",
             "-nodes", "-days", "1", "-subj", "/CN=localhost", "-addext",
             "subjectAltName=DNS:localhost,IP:127.0.0.1", "-out", str(cert), "-keyout", str(key)],
            check=True, capture_output=True,
        )
        port = int(upstream.rsplit(":", 1)[1])
        command = (
            "sed -e 's@listen 80;@listen 443 ssl; ssl_certificate /tls/cert.pem; "
            "ssl_certificate_key /tls/key.pem;@' "
            f"-e 's/backend:8000/host.docker.internal:{port}/' "
            "/repo.conf > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"
        )
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--pull", "never", "--name", name,
             "-p", f"127.0.0.1:{edge_port}:443",
             "-v", f"{ROOT / 'frontend' / 'nginx.conf'}:/repo.conf:ro",
             "-v", f"{folder}:/tls:ro", "nginx:alpine", "sh", "-ec", command],
            check=True, capture_output=True,
        )
        try:
            yield f"https://127.0.0.1:{edge_port}", cert
        finally:
            subprocess.run(["docker", "stop", name], capture_output=True, check=True, timeout=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--load-output", type=Path)
    parser.add_argument("--seconds", type=int, default=120, choices=range(5, 181), metavar="5..180")
    args = parser.parse_args()
    allowed = "https://meetingmind-smoke.localhost"
    env = {"CORS_ORIGINS": f'["{allowed}"]'}
    if args.load_output:
        env.update(SETTINGS)
    bootstrap = LOAD_BOOTSTRAP if args.load_output else None
    with local_stack(env, bootstrap) as upstream, https_edge(upstream) as (url, cert):
        context = ssl.create_default_context(cafile=str(cert))
        with httpx.Client(base_url=url, verify=context, trust_env=False, timeout=8) as client:
            for _ in range(40):
                try:
                    response = client.get("/ready")
                    if response.status_code == 200 and response.json()["status"] == "ok":
                        assert response.headers["X-Request-ID"]
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError("HTTPS endpoint did not become ready")
            assert client.get("/api/v1/meetings").status_code == 401
            for origin, expected in ((allowed, 200), ("https://denied.invalid", 400)):
                response = client.options("/api/v1/rag/ask", headers={
                    "Origin": origin, "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization, content-type",
                })
                assert response.status_code == expected, (origin, response.status_code)
                assert response.headers.get("access-control-allow-origin") == (origin if expected == 200 else None)
            print("Verified TLS, unauthenticated 401, CORS allow 200 and deny 400", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "demo_http_business_flow.py"),
             "--base-url", url, "--timeout", "60", "--profile", "local-lightweight",
             "--output", str(args.output.resolve())],
            env=dict(os.environ, SSL_CERT_FILE=str(cert)), check=False,
        ).returncode
        if result == 0 and args.load_output:
            with httpx.Client(base_url=url, verify=context, trust_env=False, timeout=8) as client:
                before = client.get("/api/_acceptance/cache").raise_for_status().json()
                load = benchmark(url, SimpleNamespace(users=4, requests=16, concurrency=[4, 8],
                                                      seconds=args.seconds), verify=context)
                after = client.get("/api/_acceptance/cache").raise_for_status().json()
            args.load_output.parent.mkdir(parents=True, exist_ok=True)
            args.load_output.write_text(json.dumps({
                "profile": "local-lightweight", "transport": "https",
                "agent_backend": "synthetic 250 ms service", "users": 4,
                "seconds_per_level_target": args.seconds, "results": load,
                "cache_window": cache_delta(before, after),
            }, indent=2) + "\n", encoding="utf-8")
        return result


if __name__ == "__main__":
    raise SystemExit(main())
