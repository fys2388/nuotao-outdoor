"""Sentry error monitoring configuration.

Initializes Sentry SDK if SENTRY_DSN is set in environment.
If not configured, Sentry is disabled (safe fallback).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Initialize Sentry SDK. Returns True if Sentry is active.

    Reads configuration from environment:
    - SENTRY_DSN: Sentry project DSN (required to enable)
    - SENTRY_ENVIRONMENT: Environment name (default: production)
    - SENTRY_TRACES_SAMPLE_RATE: Performance sample rate (default: 0.1)
    """
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        logger.info("Sentry disabled: SENTRY_DSN not configured")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry initialized successfully")
        return True
    except ImportError:
        logger.warning("sentry-sdk not installed; Sentry disabled")
        return False
    except Exception as e:
        logger.warning("Sentry initialization failed: %s", e)
        return False
