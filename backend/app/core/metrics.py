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

import json
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
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
# Backup Metric Sync (Status File + Backup Directory)
# ============================================
# The actual backup may be performed by any of:
#   1. Windows scheduled task (scripts/backup-database.ps1) -> writes status file
#   2. Docker backup container (docker-compose.prod.yml) -> writes .sql.gz to /backups
#   3. In-app DatabaseBackupService -> updates gauges directly
# Previously only #3 updated nuotao_last_backup_timestamp, causing false
# BackupFailed alerts. This bridge checks all sources and keeps metrics in sync.

logger = logging.getLogger(__name__)

# Source 1: status file written by backup-database.ps1 (Windows local)
BACKUP_STATUS_FILE = Path(r"E:\AI\nuotao-ai-os\backups\last_backup_status.json")
_backup_status_file_mtime: float | None = None

# Source 2: backup directories to scan for latest .sql.gz (Docker / local)
BACKUP_DIRECTORIES = [
    Path("/backups"),                      # Production: backup container mount (read-only in api)
    Path(r"E:\AI\nuotao-ai-os\backups\database"),  # Windows local: ps1 script output
    Path("backups/database"),              # Relative fallback
]
_backup_dir_latest_mtime: float | None = None


def _find_latest_backup_file() -> tuple[Path, float] | None:
    """Scan candidate backup directories and return the newest .sql.gz file
    along with its mtime, or None if no backup files exist."""
    latest: tuple[Path, float] | None = None
    for directory in BACKUP_DIRECTORIES:
        try:
            if not directory.exists() or not directory.is_dir():
                continue
            for f in directory.glob("*.sql.gz"):
                try:
                    mtime = f.stat().st_mtime
                    if latest is None or mtime > latest[1]:
                        latest = (f, mtime)
                except OSError:
                    continue
        except OSError:
            continue
    return latest


def sync_backup_metrics_from_file() -> None:
    """Read the backup status file written by backup-database.ps1 and
    update Prometheus gauges if the file is newer than the last sync."""
    global _backup_status_file_mtime
    try:
        if not BACKUP_STATUS_FILE.exists():
            return
        mtime = BACKUP_STATUS_FILE.stat().st_mtime
        if _backup_status_file_mtime is not None and mtime <= _backup_status_file_mtime:
            return  # No change since last sync
        _backup_status_file_mtime = mtime

        status = json.loads(BACKUP_STATUS_FILE.read_text(encoding="utf-8-sig"))
        if not status.get("success") or not status.get("timestamp"):
            return

        ts = float(status["timestamp"])
        last_backup_timestamp.set(ts)
        if status.get("compressed_size_bytes"):
            last_backup_size_bytes.set(int(status["compressed_size_bytes"]))
        logger.info(
            "Backup metrics synced from status file: timestamp=%s file=%s",
            status.get("timestamp_iso", ts),
            status.get("file_name", "unknown"),
        )
    except Exception as e:
        logger.warning("Failed to sync backup metrics from status file: %s", e)


def sync_backup_metrics_from_directory() -> None:
    """Scan backup directories for the newest .sql.gz file and update
    Prometheus gauges if it is newer than the last synced file.
    This is the primary source in production (Docker backup container)."""
    global _backup_dir_latest_mtime
    try:
        latest = _find_latest_backup_file()
        if latest is None:
            return
        backup_file, mtime = latest
        if _backup_dir_latest_mtime is not None and mtime <= _backup_dir_latest_mtime:
            return  # No newer backup since last sync
        _backup_dir_latest_mtime = mtime

        size_bytes = backup_file.stat().st_size
        last_backup_timestamp.set(mtime)
        last_backup_size_bytes.set(size_bytes)
        logger.info(
            "Backup metrics synced from directory: file=%s mtime=%s size=%d bytes",
            backup_file.name,
            mtime,
            size_bytes,
        )
    except Exception as e:
        logger.warning("Failed to sync backup metrics from directory: %s", e)


def sync_backup_metrics() -> None:
    """Unified entry point: sync backup metrics from all available sources.
    Called on app startup and on every /metrics scrape."""
    sync_backup_metrics_from_file()
    sync_backup_metrics_from_directory()

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

    # Sync backup metrics from status file / backup directory on startup
    # (bridges external backup scripts and Docker backup container -> Prometheus)
    sync_backup_metrics()

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        """Prometheus metrics endpoint."""
        # Re-sync on every scrape so backups taken while the app runs are reflected
        sync_backup_metrics()
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
