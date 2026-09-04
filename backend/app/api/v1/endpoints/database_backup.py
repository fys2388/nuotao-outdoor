"""Database backup API endpoints.

Provides endpoints for:
- Triggering a manual backup
- Listing available backups
- Getting backup service status
- Downloading a backup file
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.services.database_backup_service import get_backup_service

router = APIRouter(prefix="/backup", tags=["database-backup"])


@router.post("/run", summary="手动触发数据库备份")
async def run_backup() -> dict:
    """Trigger a manual database backup.

    Returns:
        Backup result with file path, size, duration, etc.
    """
    backup_service = get_backup_service()
    result = await backup_service.create_backup()

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup failed: {result['error']}",
        )

    return result


@router.get("/list", summary="列出所有备份文件")
async def list_backups() -> dict:
    """List all available database backups.

    Returns:
        List of backup files with size, date, age, etc.
    """
    backup_service = get_backup_service()
    backups = backup_service.list_backups()
    return {
        "total": len(backups),
        "backups": backups,
    }


@router.get("/status", summary="获取备份服务状态")
async def backup_status() -> dict:
    """Get backup service status.

    Returns:
        Backup service status including latest backup, scheduler status, etc.
    """
    backup_service = get_backup_service()
    return backup_service.get_backup_status()


@router.get("/download/{file_name}", summary="下载备份文件")
async def download_backup(file_name: str) -> FileResponse:
    """Download a backup file by name.

    Args:
        file_name: Name of the backup file (e.g. nuotao_20260902_095623.sql.gz).

    Returns:
        Backup file as download.
    """
    backup_service = get_backup_service()
    backup_file = backup_service.backup_dir / file_name

    # Security: prevent path traversal
    if not backup_file.resolve().is_relative_to(backup_service.backup_dir.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file name",
        )

    if not backup_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup file not found: {file_name}",
        )

    return FileResponse(
        path=str(backup_file),
        filename=file_name,
        media_type="application/gzip",
    )
