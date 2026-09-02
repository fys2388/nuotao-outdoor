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

    # WooCommerce REST API credentials (read-only consumer). Kept as Settings
    # fields so gates/readiness checks read the SAME .env-backed config as the
    # rest of the app instead of only process environment variables.
    woocommerce_base_url: str = ""
    woocommerce_consumer_key: str = ""
    woocommerce_consumer_secret: str = ""

    # WooCommerce webhook consumer secret (HMAC-SHA256 signature verification).
    # MUST be overridden in staging/production environments.
    woocommerce_webhook_secret: str = "dev-webhook-secret-change-me"

    # --- M5.16 Scrapling scraping capability (compliance-gated) --------------
    # Compliance review (docs/M5.16) approved a low-frequency, robots.txt-
    # respecting, public-fields-only scrape. This is DISABLED by default; the
    # code skeleton exists but never runs unless explicitly enabled + domains
    # are allowlisted. A domain whitelist with a single proxy-less plain
    # request is used - no stealth / Cloudflare bypass / login-wall scraping.
    scraping_enabled: bool = False
    scraping_allowed_domains: list[str] = []  # e.g. ["detail.1688.com"]
    scraping_qps_per_domain: float = 0.5  # min 2s between requests per domain
    scraping_max_urls_per_job: int = 50
    scraping_global_concurrency: int = 2
    scraping_connect_timeout_seconds: float = 10.0
    scraping_read_timeout_seconds: float = 30.0
    scraping_max_retries: int = 2  # idempotent GET retries, exponential backoff
    scraping_circuit_failures: int = 5  # consecutive failures before circuit opens
    scraping_circuit_cooldown_seconds: int = 600

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
    # --- M5.4 Alert Service thresholds (config-driven, never hardcoded) ----
    # An alert is opened when the live queue/worker/metric state crosses one
    # of these thresholds; the same problem keeps ONE active alert (dedup by
    # workspace + agent + alert_type + resource) until it is resolved.
    alert_queue_depth_threshold: int = 100
    alert_oldest_pending_age_ms: int = 600000
    alert_worker_dead_timeout_seconds: int = 60
    alert_failure_rate_threshold: float = 0.15
    alert_retry_rate_threshold: float = 0.50
    alert_dlq_growth_threshold: int = 10
    alert_llm_latency_threshold_ms: int = 30000
    alert_budget_warning_threshold: Decimal = Decimal("0.80")
    alert_approval_timeout_threshold_seconds: int = 3600
    alert_stats_window_minutes: int = 60
    alert_max_severity_queue_backlog: int = 200

    # Window (minutes) used for throughput / success / failure rates in stats.
    queue_stats_window_minutes: int = 60

    # --- M5.5 Agent Platform Productionization --------------------------------
    # Alert Scheduler: a resident background loop that runs the existing
    # ``evaluate_alerts()`` on a configurable interval. Empty scope lists mean
    # "all workspaces / all agents"; the scheduler is never a business action.
    agent_alert_scheduler_enabled: bool = True
    agent_alert_interval_seconds: int = 60
    alert_workspace_ids: list[str] = []
    alert_agent_ids: list[str] = []

    # Approval Center RBAC (M5.5). When enabled, approve/reject checks the
    # actor's workspace roles server-side (403 when the permission is missing).
    # A workspace with NO enabled roles stays in the legacy "any operator"
    # mode for backwards compatibility; production must configure roles.
    approval_rbac_enabled: bool = True

    # Approval SLA (M5.5): pending -> warning -> expired. Per-type rows in
    # ``agent_approval_slas`` override these defaults.
    approval_sla_enabled: bool = True

    # Actor identity (M5.8/M5.14). AUTHENTICATION_GAP: with ``body`` the
    # approval/audit actor is declared in the request body (staging-safe,
    # RBAC still enforced server-side). With ``header`` the actor MUST come
    # from a cryptographically verified RS256 JWT (Clerk, injected by
    # Cloudflare Access / a trusted proxy) - request body actors and raw
    # ``X-Actor`` values are never accepted. Secrets must never live here.
    actor_provider: str = "body"  # body | header
    actor_header_name: str = "X-Actor"  # deprecated legacy seam; unused in header mode

    # --- M5.14 Identity Foundation (STAGING ONLY) ----------------------------
    # Trusted identity header injected by Cloudflare Access / trusted proxy.
    # Its value MUST be a signed RS256 JWT (Clerk) - never a raw actor string.
    trusted_identity_header: str = "CF-Access-Jwt-Assertion"
    # Clerk JWKS / issuer / audience. Empty in dev: the header provider fails
    # closed (401) until staging identity is configured - there is NO fallback
    # to the request body actor. Defaults never hardcode a real Clerk URL.
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    jwt_clock_skew_seconds: int = 30
    jwks_cache_ttl_seconds: int = 300
    jwks_fetch_timeout_seconds: float = 5.0
    approval_default_warning_seconds: int = 3600
    approval_default_expire_seconds: int = 86400

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

    # --- Cache / Redis 缓存配置 ---
    cache_enabled: bool = True
    cache_max_connections: int = 20
    cache_default_ttl: int = 300  # 5 分钟

    # --- M6 Image Generation (pluggable gateway, cost-guarded) --------------
    # Default model: doubao-seedream-4-0-250828 (Volcengine Ark, 200 free images quota, ¥0.20/img).
    image_gen_default_model: str = "doubao-seedream-4-0-250828"
    image_gen_monthly_budget_cny: Decimal = Decimal("100.00")
    image_gen_high_cost_threshold_cny: Decimal = Decimal("0.15")
    image_gen_storage_dir: str = "data/generated_images"
    image_gen_timeout_seconds: float = 60.0
    image_gen_max_retries: int = 2

    # Image generation API keys (read from .env; never hardcode).
    dashscope_api_key: str = ""
    dashscope_workspace_id: str = ""
    volcengine_api_key: str = ""
    volcengine_ark_endpoint: str = ""

    @property
    def is_production(self) -> bool:
        """Return True when running in a production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
