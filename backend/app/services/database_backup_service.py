"""Database backup service for Nuotao AI OS.

Supports Neon PostgreSQL cloud database backup via pg_dump, with:
- Compressed backup files (gzip)
- Retention policy (default 30 days)
- Prometheus metrics update on success/failure
- Manual trigger and scheduled execution
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.metrics import record_backup_failure, record_backup_success

logger = logging.getLogger(__name__)

settings = get_settings()


class DatabaseBackupService:
    """Service for managing database backups."""

    def __init__(
        self,
        backup_dir: str | None = None,
        retention_days: int | None = None,
        max_backups: int | None = None,
        pg_dump_path: str | None = None,
    ) -> None:
        """Initialize the backup service.

        Args:
            backup_dir: Directory to store backup files.
            retention_days: Number of days to retain backups.
            max_backups: Maximum number of backup files to keep.
            pg_dump_path: Path to pg_dump executable.
        """
        self.backup_dir = Path(backup_dir or settings.backup_dir)
        self.retention_days = retention_days if retention_days is not None else settings.backup_retention_days
        self.max_backups = max_backups if max_backups is not None else settings.backup_max_files
        self.pg_dump_path = pg_dump_path or self._find_pg_dump()
        self._scheduler_task: asyncio.Task[None] | None = None
        self._running = False

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _find_pg_dump() -> str:
        """Find pg_dump executable on the system."""
        # Check common paths
        common_paths = [
            r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
            r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
            r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
            "/usr/bin/pg_dump",
            "/usr/local/bin/pg_dump",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

        # Try PATH
        pg_dump = shutil.which("pg_dump")
        if pg_dump:
            return pg_dump

        logger.warning("pg_dump not found, backups will fail")
        return "pg_dump"

    def _parse_database_url(self) -> dict[str, Any]:
        """Parse DATABASE_URL into connection parameters."""
        url = settings.database_url
        # Format: postgresql+asyncpg://user:password@host:port/dbname?params
        # Remove asyncpg driver prefix
        clean_url = url.replace("postgresql+asyncpg://", "postgresql://")
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(clean_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
            "dbname": parsed.path.lstrip("/") or "postgres",
            "params": parse_qs(parsed.query),
        }

    async def create_backup(self) -> dict[str, Any]:
        """Create a database backup.

        Returns:
            Dict with backup details (success, file_path, size, duration, error).
        """
        start_time = time.perf_counter()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"nuotao_{timestamp}.sql"
        backup_file_gz = self.backup_dir / f"nuotao_{timestamp}.sql.gz"

        logger.info("Starting database backup: %s", backup_file_gz.name)

        try:
            db_config = self._parse_database_url()

            # Build pg_dump command
            cmd = [
                self.pg_dump_path,
                "-h", db_config["host"],
                "-p", str(db_config["port"]),
                "-U", db_config["user"],
                "-d", db_config["dbname"],
                "-F", "p",  # Plain text format
                "-c",  # Clean (drop) before create
                "-C",  # Include create database
                "--no-owner",  # Don't set ownership
                "--no-acl",  # Don't include privileges
                "-f", str(backup_file),
            ]

            # Set environment variables for password and SSL
            env = os.environ.copy()
            env["PGPASSWORD"] = db_config["password"]
            if db_config["params"].get("ssl") == ["require"]:
                env["PGSSLMODE"] = "require"

            # Run pg_dump
            logger.info("Running pg_dump: host=%s db=%s", db_config["host"], db_config["dbname"])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"pg_dump failed (code {process.returncode}): {error_msg}")

            if not backup_file.exists():
                raise RuntimeError(f"Backup file not generated: {backup_file}")

            # Compress backup
            original_size = backup_file.stat().st_size
            logger.info("Compressing backup (original: %.2f MB)", original_size / 1024 / 1024)

            with open(backup_file, "rb") as f_in:
                with gzip.open(backup_file_gz, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            backup_file.unlink()

            compressed_size = backup_file_gz.stat().st_size
            duration = time.perf_counter() - start_time

            # Verify backup integrity
            try:
                with gzip.open(backup_file_gz, "rb") as f:
                    # Read first chunk to verify it's valid gzip
                    f.read(4096)
                logger.info("Backup integrity verified")
            except Exception as e:
                raise RuntimeError(f"Backup integrity verification failed: {e}")

            # Clean old backups
            cleaned = self._clean_old_backups()

            # Update Prometheus metrics
            record_backup_success(
                timestamp=time.time(),
                size_bytes=compressed_size,
            )

            result = {
                "success": True,
                "file_path": str(backup_file_gz),
                "file_name": backup_file_gz.name,
                "original_size_bytes": original_size,
                "compressed_size_bytes": compressed_size,
                "duration_seconds": round(duration, 2),
                "cleaned_old_backups": cleaned,
                "error": None,
            }

            logger.info(
                "Database backup completed: %s (%.2f MB -> %.2f MB, %.2fs)",
                backup_file_gz.name,
                original_size / 1024 / 1024,
                compressed_size / 1024 / 1024,
                duration,
            )

            return result

        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error("Database backup failed after %.2fs: %s", duration, e, exc_info=True)

            # Record failure metric
            record_backup_failure()

            # Clean up partial files
            if backup_file.exists():
                backup_file.unlink()
            if backup_file_gz.exists():
                backup_file_gz.unlink()

            return {
                "success": False,
                "file_path": None,
                "file_name": None,
                "original_size_bytes": 0,
                "compressed_size_bytes": 0,
                "duration_seconds": round(duration, 2),
                "cleaned_old_backups": 0,
                "error": str(e),
            }

    def _clean_old_backups(self) -> int:
        """Remove backups older than retention_days and enforce max_backups limit.

        Returns:
            Number of backups deleted.
        """
        deleted = 0
        cutoff = time.time() - (self.retention_days * 86400)

        # Delete old backups
        for backup_file in self.backup_dir.glob("*.sql.gz"):
            if backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                deleted += 1
                logger.info("Deleted old backup: %s", backup_file.name)

        # Enforce max backups limit
        all_backups = sorted(
            self.backup_dir.glob("*.sql.gz"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if len(all_backups) > self.max_backups:
            for old_backup in all_backups[self.max_backups:]:
                old_backup.unlink()
                deleted += 1
                logger.info("Deleted excess backup: %s", old_backup.name)

        return deleted

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backups.

        Returns:
            List of backup info dicts.
        """
        backups = []
        for backup_file in sorted(
            self.backup_dir.glob("*.sql.gz"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        ):
            stat = backup_file.stat()
            backups.append({
                "file_name": backup_file.name,
                "file_path": str(backup_file),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "age_hours": round((time.time() - stat.st_mtime) / 3600, 1),
            })
        return backups

    def get_backup_status(self) -> dict[str, Any]:
        """Get backup service status.

        Returns:
            Dict with backup status info.
        """
        backups = self.list_backups()
        latest = backups[0] if backups else None
        return {
            "total_backups": len(backups),
            "latest_backup": latest,
            "backup_dir": str(self.backup_dir),
            "retention_days": self.retention_days,
            "max_backups": self.max_backups,
            "pg_dump_path": self.pg_dump_path,
            "scheduler_running": self._running,
        }

    async def start_scheduler(self, hour: int = 2, minute: int = 0) -> None:
        """Start the backup scheduler.

        Runs backup daily at the specified time.

        Args:
            hour: Hour of day to run backup (0-23).
            minute: Minute of hour to run backup (0-59).
        """
        if self._running:
            logger.warning("Backup scheduler already running")
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(hour, minute),
            name="database-backup-scheduler",
        )
        logger.info("Database backup scheduler started (daily at %02d:%02d)", hour, minute)

    async def stop_scheduler(self) -> None:
        """Stop the backup scheduler."""
        self._running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._scheduler_task = None
        logger.info("Database backup scheduler stopped")

    async def _scheduler_loop(self, hour: int, minute: int) -> None:
        """Scheduler loop that runs backup daily at specified time."""
        while self._running:
            try:
                # Calculate seconds until next run
                now = datetime.now()
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    # Next run is tomorrow
                    next_run = next_run.replace(day=next_run.day + 1)

                wait_seconds = (next_run - now).total_seconds()
                logger.info("Next database backup scheduled in %.1f hours", wait_seconds / 3600)

                # Wait until next run (check every 60 seconds for cancellation)
                while wait_seconds > 0 and self._running:
                    sleep_time = min(60, wait_seconds)
                    await asyncio.sleep(sleep_time)
                    wait_seconds -= sleep_time

                if not self._running:
                    break

                # Run backup
                logger.info("Running scheduled database backup")
                result = await self.create_backup()
                if result["success"]:
                    logger.info("Scheduled backup completed successfully")
                else:
                    logger.error("Scheduled backup failed: %s", result["error"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Backup scheduler error: %s", e, exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retry


# Global singleton instance
_backup_service: DatabaseBackupService | None = None


def get_backup_service() -> DatabaseBackupService:
    """Get the global backup service instance."""
    global _backup_service
    if _backup_service is None:
        _backup_service = DatabaseBackupService()
    return _backup_service
