"""Prometheus metrics definitions.

Exposed via GET /metrics. To make this work under multi-worker uvicorn,
set PROMETHEUS_MULTIPROC_DIR env var (already done in Dockerfile.prod) and
mount a writable dir at that path.

For dev (single-worker / pytest), it falls back to in-process counters.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    CollectorRegistry,
)

# ---- metric definitions ----

# Task runs (by terminal status)
RUN_TOTAL = Counter(
    "spiderman_task_runs_total",
    "Total task runs by terminal status",
    ["status"],
)

# Run duration histogram (only finished runs)
RUN_DURATION = Histogram(
    "spiderman_run_duration_seconds",
    "Distribution of task-run wall durations",
    buckets=(1, 5, 30, 120, 600, 3600, 7200, float("inf")),
)

# Active runs gauge (sampled). Use multiprocess_mode='liveall' so all uvicorn
# workers' values are summed by the exporter (correct for cluster-wide aggregate).
ACTIVE_RUNS = Gauge(
    "spiderman_active_runs",
    "Currently RUNNING / DISPATCHING / PENDING runs",
    multiprocess_mode="liveall",
)

WORKERS_ONLINE = Gauge(
    "spiderman_workers_online",
    "Workers in ONLINE status",
    multiprocess_mode="liveall",
)

# HTTP request latency
HTTP_REQ_DURATION = Histogram(
    "spiderman_http_request_duration_seconds",
    "HTTP request duration by route+method+status",
    ["method", "path", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


# ---- middleware ----


@asynccontextmanager
async def measure_http(method: str, path: str):
    start = time.perf_counter()
    status = 500
    try:
        yield lambda code: status_setter(status_holder, code)  # noqa: F821
    finally:
        pass


# Simpler: a callable middleware. Used directly in app.main.
async def http_metrics_middleware(request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        status = 500
        raise
    finally:
        duration = time.perf_counter() - start
        # Use route template if matched, else raw path (cap label cardinality).
        route = getattr(request.scope.get("route"), "path", None) or request.url.path
        if len(route) > 80:
            route = route[:80]
        try:
            HTTP_REQ_DURATION.labels(
                method=request.method, path=route, status=str(status)
            ).observe(duration)
        except Exception:
            pass


# ---- exporter ----


def render_metrics() -> tuple[bytes, str]:
    """Return (payload, content_type) for /metrics endpoint."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


# ---- helpers used by other modules ----


def record_run_terminal(status: str, duration_seconds: float | None) -> None:
    """Call when a task run reaches a terminal state (success/failed/...)."""
    try:
        RUN_TOTAL.labels(status=str(status)).inc()
        if duration_seconds is not None and duration_seconds >= 0:
            RUN_DURATION.observe(duration_seconds)
    except Exception:
        pass


def set_active_runs(n: int) -> None:
    try:
        ACTIVE_RUNS.set(n)
    except Exception:
        pass


def set_workers_online(n: int) -> None:
    try:
        WORKERS_ONLINE.set(n)
    except Exception:
        pass
