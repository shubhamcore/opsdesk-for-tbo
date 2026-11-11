"""Observability: request tracing, structured logs, metrics and abuse control.

Everything here is measured, not simulated:

* ``X-Request-ID`` is generated (or propagated) for every request and echoed in
  the structured log line, so a UI action can be traced to a server log entry.
* Latency and status codes are recorded per route template, which is what
  ``GET /api/metrics`` exposes in Prometheus text format.
* Auth endpoints are rate limited per client address with a fixed one-minute
  window; the limit is configurable and can be disabled with
  ``OPSDESK_RATE_LIMIT_PER_MINUTE=0``.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from backend.config import settings

logger = logging.getLogger("opsdesk.access")

STARTED_AT = time.time()

# route template -> status class -> count
REQUEST_COUNTS: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
# route template -> list of durations in milliseconds (bounded per route)
LATENCIES: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))
RATE_LIMITED = {"count": 0}
_AUTH_WINDOW: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))
_AUTH_PATHS = ("/api/auth/login", "/api/auth/demo-login")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # ``frame-ancestors`` is deliberately omitted: the console is designed to run
    # inside preview panes and partner portals, and an ancestor directive of ``*``
    # still refuses opaque origins (``about:blank``, ``srcdoc``), which would break
    # exactly that embedding. Everything else is locked to same-origin.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self' data:"
    ),
}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    # collapse identifiers so metrics do not explode per ticket id
    parts = []
    for part in path.split("/"):
        parts.append("{id}" if part.isdigit() else part)
    return "/".join(parts)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()

        # ------------------------------------------------------- rate limiting
        if request.url.path in _AUTH_PATHS and settings.rate_limit_per_minute > 0:
            now = time.monotonic()
            bucket = _AUTH_WINDOW[_client_key(request)]
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= settings.rate_limit_per_minute:
                RATE_LIMITED["count"] += 1
                retry_after = max(1, int(60 - (now - bucket[0])))
                response: Response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Too many sign-in attempts. Retry in {retry_after}s "
                            f"(limit {settings.rate_limit_per_minute}/min per client)."
                        )
                    },
                    headers={"Retry-After": str(retry_after)},
                )
                self._finish(request, response, request_id, started, status=429)
                return response
            bucket.append(now)

        try:
            response = await call_next(request)
        except Exception:
            RATE_LIMITED.setdefault("errors", 0)
            RATE_LIMITED["errors"] += 1
            logger.exception(
                json.dumps({"event": "request.error", "request_id": request_id, "path": request.url.path})
            )
            raise

        self._finish(request, response, request_id, started, status=response.status_code)
        return response

    def _finish(self, request: Request, response: Response, request_id: str, started: float, *, status: int) -> None:
        duration_ms = (time.perf_counter() - started) * 1000
        template = _route_template(request)
        REQUEST_COUNTS[template][f"{status // 100}xx"] += 1
        LATENCIES[template].append(duration_ms)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if not request.url.path.startswith("/assets/"):
            logger.info(
                json.dumps(
                    {
                        "event": "request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "route": template,
                        "status": status,
                        "duration_ms": round(duration_ms, 2),
                    }
                )
            )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def prometheus_text(gauge_provider=None) -> str:
    """Prometheus exposition format. ``gauge_provider`` adds live business gauges."""
    lines: list[str] = []

    def emit(name: str, value: float, labels: str = "", help_text: str | None = None) -> None:
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{labels} {value}")

    emit(
        "opsdesk_uptime_seconds",
        round(time.time() - STARTED_AT, 2),
        help_text="Seconds since the process started",
    )
    lines.append("# TYPE opsdesk_http_requests_total counter")
    for route, statuses in sorted(REQUEST_COUNTS.items()):
        for status_class, count in sorted(statuses.items()):
            lines.append(
                f'opsdesk_http_requests_total{{route="{route}",status="{status_class}"}} {count}'
            )
    lines.append("# TYPE opsdesk_http_request_duration_ms summary")
    for route, durations in sorted(LATENCIES.items()):
        values = list(durations)
        if not values:
            continue
        lines.append(f'opsdesk_http_request_duration_ms{{route="{route}",quantile="0.5"}} {round(_percentile(values, 50), 2)}')
        lines.append(f'opsdesk_http_request_duration_ms{{route="{route}",quantile="0.95"}} {round(_percentile(values, 95), 2)}')
        lines.append(f'opsdesk_http_request_duration_ms{{route="{route}",quantile="1.0"}} {round(max(values), 2)}')
    emit("opsdesk_rate_limited_total", RATE_LIMITED["count"], help_text="Sign-in attempts rejected by the limiter")
    if gauge_provider is not None:
        for name, value in gauge_provider().items():
            emit(name, value)
    return "\n".join(lines) + "\n"
