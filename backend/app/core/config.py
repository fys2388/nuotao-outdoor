"""Application settings loaded from environment variables / .env files."""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Nuotao AI OS backend.

    Values are read from environment variables (mapped case-insensitively,
    e.g. ``DATABASE_URL`` -> ``database_url``) or from ``.env`` files in the
    current working directory or its parent.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nuotao AI OS"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://nuotao:nuotao_dev_password@localhost:5432/nuotao"
    redis_url: str = "redis://localhost:6379/0"

    # WooCommerce webhook consumer secret (HMAC-SHA256 signature verification).
    # MUST be overridden in staging/production environments.
    woocommerce_webhook_secret: str = "dev-webhook-secret-change-me"

    # Payment fee estimation used when the payment provider fee is unknown.
    payment_fee_rate: Decimal = Decimal("0.029")
    payment_fee_fixed: Decimal = Decimal("0.30")

    # --- LLM Gateway (M2.2): multi-provider, vendor lock-in avoided ---------
    # Primary provider drives default routing; the fallback is used when the
    # primary is unreachable (network / 5xx / rate limit), never on auth errors.
    llm_provider: str = "openai"  # openai | deepseek
    llm_fallback_provider: str = "deepseek"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_default_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 1500

    # --- M5.1 Agent Runtime production hardening ------------------------------
    # Task queue: Redis Streams for Phase 1 (modular monolith; no Celery/Kafka).
    # ``task_queue_backend`` may be ``redis`` (default) or ``memory`` (tests).
    task_queue_backend: str = "redis"
    task_queue_stream: str = "nuotao:agent-tasks"
    task_queue_group: str = "nuotao:agent-worker"
    task_queue_retry_key: str = "nuotao:agent-retry"
    task_queue_maxlen: int = 2000
    task_queue_poll_ms: int = 2000
    task_queue_defer_delay: int = 2
    # Crash recovery: messages idle in the consumer-group PEL for longer than
    # this are reclaimed and reprocessed (the DB task row keeps it idempotent).
    task_queue_reclaim_idle_ms: int = 60000
    task_queue_reclaim_batch: int = 100
    # Reconcile: pending tasks whose enqueued_at is older than this are
    # re-enqueued by the sweeper (DB is the source of truth; the queue is an
    # accelerator). Crash window between DB commit and XADD is covered too.
    task_queue_reconcile_idle_seconds: int = 60
    # Message-level dedup (M5.3): stable per (task, attempt) identity held in
    # Redis with a TTL. This is an optimization on top of the DB guard - the
    # PostgreSQL task row remains the business source of truth.
    task_queue_dedup_key_prefix: str = "nuotao:agent-dedup"
    task_queue_dedup_ttl_seconds: int = 900
    worker_enabled: bool = False  # start the resident worker in the API lifespan
    worker_concurrency: int = 4
    worker_id: str = "worker-1"

    # --- M5.3 Worker registry / heartbeat (Redis-backed, no new tables) ------
    # A worker is considered dead when no heartbeat arrived for longer than
    # ``worker_heartbeat_timeout_seconds``. Keys expire after
    # ``worker_registry_ttl_seconds`` so crashed workers do not linger forever.
    worker_registry_prefix: str = "nuotao:agent-worker"
    worker_heartbeat_timeout_seconds: int = 30
    worker_heartbeat_interval_seconds: int = 10
    worker_registry_ttl_seconds: int = 120
    # Throttle ``agent.queue.worker_heartbeat`` events (they are audit rows).
    worker_heartbeat_event_interval_seconds: int = 60

    # --- M5.3 Queue health thresholds (config-driven, never hardcoded) --------
    queue_health_max_pending: int = 100
    queue_health_max_dead_letters: int = 50
    queue_health_oldest_pending_ms: int = 600000
    queue_health_oldest_running_ms: int = 600000
    queue_health_max_stale_workers: int = 0
    # Window (minutes) used for throughput / success / failure rates in stats.
    queue_stats_window_minutes: int = 60

    # Default agent policies (config-driven; overridable per agent in the DB).
    agent_default_execution_timeout: int = 300
    agent_default_approval_timeout: int = 86400
    agent_default_max_concurrent: int = 3
    agent_default_max_context_size: int = 20000
    agent_default_retry_policy: str = "standard"
    agent_default_monthly_budget: Decimal = Decimal("100.00")
    agent_default_max_cost_per_execution: Decimal = Decimal("5.00")
    agent_default_budget_alert_threshold: Decimal = Decimal("0.80")

    # Default "standard" retry policy (per-workspace, versioned).
    retry_standard_max_attempts: int = 3
    retry_standard_backoff_base: int = 2
    retry_standard_backoff_multiplier: Decimal = Decimal("2.0")
    retry_standard_max_backoff: int = 60

    @property
    def is_production(self) -> bool:
        """Return True when running in a production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
