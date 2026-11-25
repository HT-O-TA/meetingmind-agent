"""Process-local Prometheus metrics for the HTTP boundary."""
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from starlette.requests import Request

from app.core.middleware import route_template

registry = CollectorRegistry()
requests = Counter("meetingmind_http_requests", "Completed HTTP requests", ("method", "route", "status"), registry=registry)
duration = Histogram(
    "meetingmind_http_duration_seconds", "Elapsed time until the ASGI request ends",
    ("method", "route"),
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30, 60, 120, 300),
    registry=registry,
)
in_flight = Gauge("meetingmind_http_in_flight_requests", "Active HTTP requests", registry=registry)
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


class HttpMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 499

        async def record_start(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        in_flight.inc()
        try:
            await self.app(scope, receive, record_start)
        except Exception:
            if status == 499:
                status = 500
            raise
        finally:
            in_flight.dec()
            method = scope["method"] if scope["method"] in METHODS else "OTHER"
            route = route_template(Request(scope))
            requests.labels(method, route, str(status)).inc()
            duration.labels(method, route).observe(time.perf_counter() - started)
