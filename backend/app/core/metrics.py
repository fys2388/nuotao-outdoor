"""Prometheus metrics collection and exposure for Nuotao AI OS.

Provides:
- HTTP request metrics (count, latency, active requests)
- LLM/AI usage metrics (request count, tokens, cost, latency)
- Task queue metrics (queue length, task count, failures)
- Worker heartbeat metrics
- Database connection pool metrics
- /metrics endpoint for Prometheus scraping
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    values,
)

# ============================================
# HTTP Request Metrics
# ============================================

http_requests_total = Counter(
    "nuotao_http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "nuotao_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

http_requests_in_progress = Gauge(
    "nuotao_http_requests_in_progress",
    "Number of HTTP requests currently in progress",
    ["method"],
)

http_request_size_bytes = Histogram(
    "nuotao_http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "path"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

http_response_size_bytes = Histogram(
    "nuotao_http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "path", "status"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

# ============================================
# LLM / AI Usage Metrics
# ============================================

llm_requests_total = Counter(
    "nuotao_llm_requests_total",
    "Total number of LLM API requests",
    ["provider", "model", "agent", "status"],
)

llm_request_duration_seconds = Histogram(
    "nuotao_llm_request_duration_seconds",
    "LLM API request duration in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

llm_tokens_total = Counter(
    "nuotao_llm_tokens_total",
    "Total number of LLM tokens used",
    ["provider", "model", "type"],  # type: prompt, completion, total
)

llm_cost_usd_total = Counter(
    "nuotao_llm_cost_usd_total",
    "Total LLM API cost in USD",
    ["provider", "model"],
)

llm_monthly_cost_usd = Gauge(
    "nuotao_llm_monthly_cost_usd",
    "Current month LLM API cost in USD",
    ["provider"],
)

# ============================================
# Agent Metrics
# ============================================

agent_runs_total = Counter(
    "nuotao_agent_runs_total",
    "Total number of agent runs",
    ["agent_id", "status"],  # status: success, failed, pending
)

agent_run_duration_seconds = Histogram(
    "nuotao_agent_run_duration_seconds",
    "Agent run duration in seconds",
    ["agent_id"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

agent_suggestions_total = Counter(
    "nuotao_agent_suggestions_total",
    "Total number of agent suggestions",
    ["agent_id", "approval_status"],  # approval_status: pending, approved, rejected
)

# ============================================
# Task Queue Metrics
# ============================================

task_queue_length = Gauge(
    "nuotao_task_queue_length",
    "Current number of tasks in the queue",
    ["queue_name"],
)

task_total = Counter(
    "nuotao_task_total",
    "Total number of tasks processed",
    ["task_type", "status"],  # status: success, failed
)

task_duration_seconds = Histogram(
    "nuotao_task_duration_seconds",
    "Task processing duration in seconds",
    ["task_type"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

task_failures_total = Counter(
    "nuotao_task_failures_total",
    "Total number of task failures",
    ["task_type", "error_type"],
)

# ============================================
# Worker Metrics
# ============================================

worker_heartbeat = Gauge(
    "nuotao_worker_heartbeat",
    "Worker heartbeat (1 if alive, 0 if dead)",
    ["worker_id"],
)

worker_tasks_processed_total = Counter(
    "nuotao_worker_tasks_processed_total",
    "Total number of tasks processed by worker",
    ["worker_id"],
)

worker_active_tasks = Gauge(
    "nuotao_worker_active_tasks",
    "Number of tasks currently being processed by worker",
    ["worker_id"],
)

# ============================================
# Database Metrics
# ============================================

db_connections_active = Gauge(
    "nuotao_db_connections_active",
    "Number of active database connections",
)

db_connections_idle = Gauge(
    "nuotao_db_connections_idle",
    "Number of idle database connections",
)

db_query_duration_seconds = Histogram(
    "nuotao_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],  # operation: select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

# ============================================
# Business Metrics
# ============================================

products_total = Gauge(
    "nuotao_products_total",
    "Total number of products in the system",
    ["status"],
)

orders_total = Counter(
    "nuotao_orders_total",
    "Total number of orders",
    ["status", "source"],
)

order_revenue_usd_total = Counter(
    "nuotao_order_revenue_usd_total",
    "Total order revenue in USD",
    ["currency"],
)

customers_total = Gauge(
    "nuotao_customers_total",
    "Total number of customers",
)

# ============================================
# Backup Metrics
# ============================================

last_backup_timestamp = Gauge(
    "nuotao_last_backup_timestamp",
    "Timestamp of the last successful backup (Unix epoch)",
)

last_backup_size_bytes = Gauge(
    "nuotao_last_backup_size_bytes",
    "Size of the last backup in bytes",
)

backups_total = Counter(
    "nuotao_backups_total",
    "Total number of backups",
    ["status"],  # status: success, failed
)

# ============================================
# System Info
# ============================================

app_info = Gauge(
    "nuotao_app_info",
    "Application information",
    ["version", "environment", "python_version"],
)

# ============================================
# Middleware
# ============================================


async def metrics_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """FastAPI middleware to collect HTTP request metrics."""
    # Skip metrics endpoint itself to avoid noise
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    path = request.url.path

    # Increment in-progress requests
    http_requests_in_progress.labels(method=method).inc()

    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        # Record request duration
        duration = time.perf_counter() - start_time
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)

        # Record request count
        status = str(response.status_code)
        http_requests_total.labels(method=method, path=path, status=status).inc()

        # Record response size
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                http_response_size_bytes.labels(method=method, path=path, status=status).observe(
                    float(content_length)
                )
            except ValueError:
                pass

        return response

    except Exception:
        # Record failed requests
        duration = time.perf_counter() - start_time
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)
        http_requests_total.labels(method=method, path=path, status="500").inc()
        raise

    finally:
        # Decrement in-progress requests
        http_requests_in_progress.labels(method=method).dec()


# ============================================
# Metrics Endpoint
# ============================================


def setup_metrics(app: FastAPI) -> None:
    """Set up Prometheus metrics for the FastAPI application.

    Adds:
    - Metrics middleware
    - /metrics endpoint
    - Initializes app_info metric
    """
    import sys

    # Add middleware
    app.middleware("http")(metrics_middleware)

    # Set app info
    app_info.labels(
        version=app.version,
        environment="production" if app.docs_url is None else "development",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    ).set(1)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        """Prometheus metrics endpoint."""
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================
# Helper Functions
# ============================================


@contextmanager
def measure_llm_request(provider: str, model: str, agent: str = "unknown"):
    """Context manager to measure LLM request duration and record metrics.

    Usage:
        with measure_llm_request("deepseek", "deepseek-chat", "product_analyst"):
            response = await llm_client.chat(...)
            # Record tokens and cost
            record_llm_tokens("deepseek", "deepseek-chat", prompt_tokens, completion_tokens)
            record_llm_cost("deepseek", "deepseek-chat", cost_usd)
    """
    start_time = time.perf_counter()
    try:
        yield
        duration = time.perf_counter() - start_time
        llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
        llm_requests_total.labels(provider=provider, model=model, agent=agent, status="success").inc()
    except Exception:
        duration = time.perf_counter() - start_time
        llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
        llm_requests_total.labels(provider=provider, model=model, agent=agent, status="error").inc()
        raise


def record_llm_tokens(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Record LLM token usage metrics."""
    llm_tokens_total.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(provider=provider, model=model, type="completion").inc(completion_tokens)
    llm_tokens_total.labels(provider=provider, model=model, type="total").inc(prompt_tokens + completion_tokens)


def record_llm_cost(provider: str, model: str, cost_usd: float) -> None:
    """Record LLM API cost metrics."""
    llm_cost_usd_total.labels(provider=provider, model=model).inc(cost_usd)


@contextmanager
def measure_agent_run(agent_id: str):
    """Context manager to measure agent run duration and record metrics."""
    start_time = time.perf_counter()
    try:
        yield
        duration = time.perf_counter() - start_time
        agent_run_duration_seconds.labels(agent_id=agent_id).observe(duration)
        agent_runs_total.labels(agent_id=agent_id, status="success").inc()
    except Exception:
        duration = time.perf_counter() - start_time
        agent_run_duration_seconds.labels(agent_id=agent_id).observe(duration)
        agent_runs_total.labels(agent_id=agent_id, status="failed").inc()
        raise


@contextmanager
def measure_task(task_type: str):
    """Context manager to measure task processing duration and record metrics."""
    start_time = time.perf_counter()
    try:
        yield
        duration = time.perf_counter() - start_time
        task_duration_seconds.labels(task_type=task_type).observe(duration)
        task_total.labels(task_type=task_type, status="success").inc()
    except Exception as e:
        duration = time.perf_counter() - start_time
        task_duration_seconds.labels(task_type=task_type).observe(duration)
        task_total.labels(task_type=task_type, status="failed").inc()
        task_failures_total.labels(task_type=task_type, error_type=type(e).__name__).inc()
        raise


def record_backup_success(timestamp: float, size_bytes: int) -> None:
    """Record successful backup metrics."""
    last_backup_timestamp.set(timestamp)
    last_backup_size_bytes.set(size_bytes)
    backups_total.labels(status="success").inc()


def record_backup_failure() -> None:
    """Record failed backup metrics."""
    backups_total.labels(status="failed").inc()
