"""Shared credential loader for one-off WooCommerce / WordPress maintenance scripts.

2026-10-11 incident: 4 sets of WooCommerce API keys, 1 WordPress application
password, 1 PostgreSQL password and 1 SMTP key were found hardcoded across
~40 files. All of those credentials have been revoked. This module is the
single place that resolves them from the environment, so a script can never
carry a real secret again.

Usage (from any script/ directory file):

    from wc_env import wc_auth, wc_base_url, wp_auth

    base = wc_base_url()
    resp = requests.get(f"{base}/wp-json/wc/v3/products",
                        auth=wc_auth(), timeout=30)
    resp = requests.post(f"{base}/wp-json/wp/v2/media",
                         auth=wp_auth(), files=files, timeout=30)

If a credential is missing the script fails fast with an actionable message
instead of silently falling back to a placeholder.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo-root .env first, then backend/.env (docker/staging layout), then the
# local E2E file. Real environment variables always win over file values.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILES = (
    _REPO_ROOT / ".env",
    _REPO_ROOT / "backend" / ".env",
    _REPO_ROOT / "_local_dev.env",
)

_loaded = False


class MissingSecret(RuntimeError):
    """A required credential is not configured anywhere."""


def _load_env_files() -> None:
    """Parse .env files into os.environ without overwriting real variables."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in _ENV_FILES:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _required(name: str, *, empty_ok: bool = False) -> str:
    _load_env_files()
    value = (os.environ.get(name) or "").strip()
    if not value and not empty_ok:
        raise MissingSecret(
            f"{name} is not set. Put it in the repo-root .env "
            f"(see .env.example) or export it in your shell.\n"
            f"Never hardcode credentials in scripts - every value found in "
            f"git history is assumed compromised."
        )
    return value


# ---------------------------------------------------------------------------
# WooCommerce REST API (wc/v3)
# ---------------------------------------------------------------------------

def wc_base_url() -> str:
    """Store URL without a trailing slash, e.g. https://nuotaooutdoor.com."""
    return _required("WOOCOMMERCE_BASE_URL").rstrip("/")


def wc_api_url() -> str:
    """Full WooCommerce REST API base, e.g. https://host/wp-json/wc/v3."""
    return f"{wc_base_url()}/wp-json/wc/v3"


def wc_consumer_key() -> str:
    return _required("WOOCOMMERCE_CONSUMER_KEY")


def wc_consumer_secret() -> str:
    return _required("WOOCOMMERCE_CONSUMER_SECRET")


def wc_auth() -> tuple[str, str]:
    """(consumer_key, consumer_secret) - pass straight to requests auth=."""
    return wc_consumer_key(), wc_consumer_secret()


def wc_webhook_secret() -> str:
    """HMAC-SHA256 webhook signature secret (may be empty in dev)."""
    return _required("WOOCOMMERCE_WEBHOOK_SECRET", empty_ok=True)


# ---------------------------------------------------------------------------
# WordPress REST API (wp/v2) - needs a user + application password.
# Generated in WP Admin -> Users -> Profile -> Application Passwords.
# NOTE: a WooCommerce consumer key is NOT accepted by wp/v2 endpoints.
# ---------------------------------------------------------------------------

def wp_base_url() -> str:
    """Full WordPress REST API base, e.g. https://host/wp-json/wp/v2."""
    return f"{wc_base_url()}/wp-json/wp/v2"


def wp_username() -> str:
    return _required("WP_USERNAME", empty_ok=True)


def wp_application_password() -> str:
    """Accepts WP_APP_PASSWORD (the WP UI label) or WP_APPLICATION_PASSWORD."""
    _load_env_files()
    value = (os.environ.get("WP_APP_PASSWORD") or "").strip()
    if value:
        return value
    return _required("WP_APPLICATION_PASSWORD", empty_ok=True)


def wp_auth() -> tuple[str, str]:
    """(username, application_password) for wp/v2 Basic Auth."""
    return _required("WP_USERNAME"), wp_application_password()
