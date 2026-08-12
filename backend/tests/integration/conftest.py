"""Integration-test infrastructure for M5.2.1 production validation.

Provides REAL PostgreSQL (embedded binaries via ``pgserver``) and REAL Redis
(server binary auto-resolved: env var -> PATH -> cached download) so the
runtime, migrations and LLM gateway can be validated against production-like
services instead of SQLite/fakes. Services that cannot start (e.g. no
network for the Redis download) cause the dependent tests to skip with a
clear message; PostgreSQL always starts because ``pgserver`` ships its own
binaries.

Fixtures:
- ``pg_server``       session-scoped embedded PostgreSQL 16 instance
- ``pg_database_url`` function-scoped fresh database (migration isolation)
- ``pg_migrated``     database migrated to the latest alembic revision
- ``redis_url``       session-scoped real Redis server (fresh DB per test)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
REDIS_RELEASE_URL = (
    "https://github.com/redis-windows/redis-windows/releases/download/"
    "8.10.0/Redis-8.10.0-Windows-x64-cygwin-with-Service.zip"
)
REDIS_ARCHIVE_NAME = "redis-8.10.0-windows.zip"
REDIS_EXE_NAMES = ("redis-server.exe", "redis-server")


def _free_port() -> int:
    """Return a currently-free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# --------------------------------------------------------------------------- #
# Redis binary resolution (env -> PATH -> cached download)
# --------------------------------------------------------------------------- #


def _redis_cache_dir() -> Path:
    env_cache = os.environ.get("NUOTAO_REDIS_CACHE_DIR")
    if env_cache:
        return Path(env_cache)
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "nuotao-ai-os"
    return base / "redis"


def _download_redis(binary: Path) -> None:
    """Download and extract the Redis server + runtime DLLs once (cached).

    The Windows build is cygwin-based: ``redis-server.exe`` requires the
    bundled ``cygwin1.dll`` / ``cygssl-3.dll`` / ... next to it, so the whole
    archive is extracted (not just the executable).
    """
    cache = binary.parent
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / REDIS_ARCHIVE_NAME
    if not archive.exists():
        print(f"downloading Redis for Windows -> {archive}")
        urllib.request.urlretrieve(REDIS_RELEASE_URL, archive)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            if Path(member).name in REDIS_EXE_NAMES or member.endswith(".dll"):
                target = cache / Path(member).name
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    if not binary.exists():
        raise RuntimeError("redis-server not found inside the downloaded archive")
    (cache / ".extracted-v1").write_text("ok", encoding="utf-8")


def resolve_redis_server() -> Path | None:
    """Return a redis-server executable path or None when unavailable."""
    override = os.environ.get("NUOTAO_REDIS_SERVER_BIN")
    if override:
        candidate = Path(override)
        return candidate if candidate.exists() else None
    on_path = shutil.which("redis-server")
    if on_path:
        return Path(on_path)
    binary = _redis_cache_dir() / REDIS_EXE_NAMES[0]
    marker = binary.parent / ".extracted-v1"
    if binary.exists() and marker.exists():
        return binary
    try:
        _download_redis(binary)
        return binary
    except Exception as exc:  # noqa: BLE001 - offline environments skip
        print(f"Redis binary unavailable: {exc}")
        return None


@pytest.fixture(scope="session")
def redis_server_bin() -> Path:
    """Real redis-server binary (skips the suite when unavailable)."""
    binary = resolve_redis_server()
    if binary is None:
        pytest.skip("redis-server binary not available (set NUOTAO_REDIS_SERVER_BIN)")
    return binary


def _redis_ping(url: str) -> bool:
    import redis as redis_sync

    client = redis_sync.Redis.from_url(url, socket_connect_timeout=1)
    try:
        return bool(client.ping())
    finally:
        client.close()


@pytest.fixture()
def redis_url(redis_server_bin: Path) -> Iterator[str]:
    """Start one real Redis server; yields its URL (fresh instance per test)."""
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - trusted local binary
        [
            str(redis_server_bin),
            "--port",
            str(port),
            "--bind",
            "127.0.0.1",
            "--save",
            "",
            "--appendonly",
            "no",
            "--maxmemory",
            "128mb",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"redis://127.0.0.1:{port}/0"
    try:
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                if _redis_ping(url):
                    ready = True
                    break
            except Exception:  # noqa: BLE001 - server still booting
                time.sleep(0.3)
        if not ready:
            raise RuntimeError("redis server did not become ready")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# --------------------------------------------------------------------------- #
# Embedded PostgreSQL (pgserver) - always available once installed
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def pg_server() -> Iterator[str]:
    """Start one embedded PostgreSQL 16 instance; yields the admin URI."""
    pgserver = pytest.importorskip("pgserver")
    tmp = Path(tempfile.mkdtemp(prefix="nuotao_pg_"))
    server = pgserver.PostgresServer(tmp, cleanup_mode="delete")
    try:
        yield server.get_uri()  # postgresql://postgres:@127.0.0.1:PORT/postgres
    finally:
        server.cleanup()


async def _create_database(admin_uri: str, name: str) -> None:
    conn = await asyncpg.connect(admin_uri)
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(admin_uri: str, name: str) -> None:
    conn = await asyncpg.connect(admin_uri)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


def _async_pg_url(admin_uri: str, db_name: str) -> str:
    """PostgreSQL URL for SQLAlchemy (asyncpg driver)."""
    base = admin_uri.rsplit("/", 1)[0]
    return f"{base}/{db_name}".replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture()
async def pg_database_url(pg_server: str) -> AsyncIterator[str]:
    """Create a fresh database per test; drops it on teardown."""
    name = f"nuotao_{int(time.time() * 1000)}_{os.getpid()}"
    await _create_database(pg_server, name)
    yield _async_pg_url(pg_server, name)
    await _drop_database(pg_server, name)


# --------------------------------------------------------------------------- #
# Alembic migrations against real PostgreSQL
# --------------------------------------------------------------------------- #


def run_alembic(url: str, command: str, revision: str) -> None:
    """Run an alembic command synchronously against ``url``.

    Alembic's env.py reads the target URL from the app settings singleton;
    this runs in a worker thread so a test event loop is never re-entered.
    """
    from alembic import command as alembic_command
    from alembic.config import Config
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.database_url
    settings.database_url = url
    try:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        getattr(alembic_command, command)(cfg, revision)
    finally:
        settings.database_url = original


@pytest.fixture()
async def pg_migrated(pg_database_url: str) -> str:
    """A real PostgreSQL database migrated to the latest alembic revision."""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "head")
    return pg_database_url


def enable_redis_queue(url: str) -> None:
    """Point the app task queue at a real Redis backend for one test."""
    from app.core.config import get_settings
    from app.services import task_queue

    settings = get_settings()
    settings.task_queue_backend = "redis"
    settings.redis_url = url
    task_queue.reset_queue_backend_cache()
    task_queue.get_queue_backend()  # force creation
