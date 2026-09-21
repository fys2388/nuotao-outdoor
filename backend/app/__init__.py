"""Nuotao AI OS backend application package.

Importing this package loads ``.env`` into ``os.environ`` before any submodule
runs its module-level code.

Why this is here and not in ``app.core.config``: ``Settings`` reads ``.env``
directly through pydantic-settings, so it always sees configured values. But
roughly 40 call sites across the integration layer (WooCommerce in three
modules, Feishu, Stripe, PayPal, 1688, logistics, Sentry) read config with bare
``os.getenv(...)`` at import time, which only sees real process environment
variables. Prod supplies config solely through ``.env`` - systemd does not
inject it - so every one of those values silently fell back to its default.
Measured on prod: ``WC_CONSUMER_KEY`` was empty while ``Settings`` saw a 43-char
key, ``FEISHU_CHAT_ID``/``FEISHU_APP_ID`` were empty while ``.env`` held values.
The integrations therefore looked configured and were entirely inert, and the
agent pipeline never received real inventory data.

``app.core.config`` is not imported by every submodule, so pinning the load
there would race with import order. ``app/__init__.py`` runs first for any
``import app.*``, which is what the module-level reads depend on.
"""
from pathlib import Path

from dotenv import load_dotenv

_PACKAGE_ROOT = Path(__file__).resolve().parent
# Same search paths as Settings(env_file=(".env", "../.env")), so the two
# agree. override=False: never clobber a value already set in the process
# environment (systemd, CI, or an explicit export).
for _candidate in (_PACKAGE_ROOT.parent / ".env", _PACKAGE_ROOT.parent.parent / ".env"):
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)
