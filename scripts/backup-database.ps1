# Nuotao AI OS - PostgreSQL Database Backup Script (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File backup-database.ps1

# ========== Configuration ==========
$PG_HOST = "localhost"
$PG_PORT = "5432"
$PG_USER = "nuotao"
$PG_DB = "nuotao"
$PG_PASSWORD = "nuotao_dev_password"
$PG_BIN = "C:\Program Files\PostgreSQL\17\bin"

$BACKUP_DIR = "E:\AI\nuotao-ai-os\backups\database"
$LOG_DIR = "E:\AI\nuotao-ai-os\backups\logs"
$RETENTION_DAYS = 30
$MAX_BACKUPS = 30

$FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371"
$ENABLE_FEISHU_NOTIFY = $true

# ========== Init ==========
$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$date = Get-Date -Format "yyyy-MM-dd"
$backupFile = "$BACKUP_DIR\nuotao_$timestamp.sql"
$backupFileGz = "$backupFile.gz"
$logFile = "$LOG_DIR\backup_$date.log"

if (!(Test-Path $BACKUP_DIR)) { New-Item -ItemType Directory -Path $BACKUP_DIR -Force | Out-Null }
if (!(Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Write-Log {
    param([string]$message, [string]$level = "INFO")
    $logMessage = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$level] $message"
    Add-Content -Path $logFile -Value $logMessage -Encoding UTF8
    Write-Host $logMessage
}

function Send-FeishuNotify {
    param([string]$title, [string]$message, [string]$color = "green")
    if (!$ENABLE_FEISHU_NOTIFY) { return }
    try {
        $body = @{
            msg_type = "interactive"
            card = @{
                header = @{
                    title = @{ tag = "plain_text"; content = $title }
                    template = $color
                }
                elements = @(
                    @{
                        tag = "div"
                        text = @{ tag = "plain_text"; content = $message }
                    }
                )
            }
        } | ConvertTo-Json -Depth 10
        Invoke-RestMethod -Uri $FEISHU_WEBHOOK -Method Post -Body $body -ContentType "application/json" -TimeoutSec 10 | Out-Null
    } catch {
        Write-Log "Feishu notify failed: $_" "WARNING"
    }
}

# ========== Start Backup ==========
Write-Log "========== Database Backup Started =========="
Write-Log "Database: ${PG_USER}@${PG_HOST}:${PG_PORT}/${PG_DB}"
Write-Log "Backup dir: $BACKUP_DIR"

try {
    $env:PGPASSWORD = $PG_PASSWORD

    # 1. pg_dump
    Write-Log "Running pg_dump..."
    $pgDump = Join-Path $PG_BIN "pg_dump.exe"
    & $pgDump -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -F p -c -C -f $backupFile 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code: $LASTEXITCODE"
    }

    if (!(Test-Path $backupFile)) {
        throw "Backup file not generated: $backupFile"
    }

    $backupSize = (Get-Item $backupFile).Length
    $backupSizeMB = [math]::Round($backupSize / 1MB, 2)
    Write-Log "Backup file generated: $backupSizeMB MB"

    # 2. Compress using .NET GZipStream
    Write-Log "Compressing backup..."
    $sourceStream = [System.IO.File]::OpenRead($backupFile)
    $destStream = [System.IO.File]::Create($backupFileGz)
    $gzipStream = New-Object System.IO.Compression.GZipStream($destStream, [System.IO.Compression.CompressionMode]::Compress)
    $sourceStream.CopyTo($gzipStream)
    $gzipStream.Close()
    $sourceStream.Close()
    Remove-Item $backupFile -Force

    if (!(Test-Path $backupFileGz)) {
        throw "Compressed file not generated: $backupFileGz"
    }

    $compressedSize = (Get-Item $backupFileGz).Length
    $compressedSizeMB = [math]::Round($compressedSize / 1MB, 2)
    $compressionRatio = [math]::Round(($compressedSize / $backupSize) * 100, 1)
    Write-Log "Compressed: $compressedSizeMB MB (ratio: $compressionRatio%)"

    # 3. Verify integrity
    Write-Log "Verifying backup integrity..."
    try {
        $verifyStream = [System.IO.File]::OpenRead($backupFileGz)
        $verifyGzip = New-Object System.IO.Compression.GZipStream($verifyStream, [System.IO.Compression.CompressionMode]::Decompress)
        $verifyBuffer = New-Object byte[] 4096
        while ($verifyGzip.Read($verifyBuffer, 0, $verifyBuffer.Length) -gt 0) { }
        $verifyGzip.Close()
        $verifyStream.Close()
        Write-Log "Backup integrity verified"
    } catch {
        throw "Backup integrity verification failed: $_"
    }

    # 4. Clean old backups
    Write-Log "Cleaning backups older than $RETENTION_DAYS days..."
    $oldBackups = Get-ChildItem -Path $BACKUP_DIR -Filter "*.sql.gz" | Where-Object {
        $_.LastWriteTime -lt (Get-Date).AddDays(-$RETENTION_DAYS)
    }
    $deletedCount = 0
    foreach ($oldBackup in $oldBackups) {
        Remove-Item $oldBackup.FullName -Force
        Write-Log "Deleted old backup: $($oldBackup.Name)"
        $deletedCount++
    }
    Write-Log "Cleanup done, deleted $deletedCount old backups"

    # 5. Keep max N backups
    $allBackups = Get-ChildItem -Path $BACKUP_DIR -Filter "*.sql.gz" | Sort-Object LastWriteTime -Descending
    if ($allBackups.Count -gt $MAX_BACKUPS) {
        $backupsToDelete = $allBackups | Select-Object -Skip $MAX_BACKUPS
        foreach ($b in $backupsToDelete) {
            Remove-Item $b.FullName -Force
            Write-Log "Exceeded max, deleted: $($b.Name)"
        }
    }

    # 6. Stats
    $currentBackups = Get-ChildItem -Path $BACKUP_DIR -Filter "*.sql.gz"
    $totalSize = ($currentBackups | Measure-Object -Property Length -Sum).Sum
    $totalSizeMB = [math]::Round($totalSize / 1MB, 2)

    Write-Log "========== Database Backup Completed =========="
    Write-Log "Backup file: $(Split-Path $backupFileGz -Leaf)"
    Write-Log "Original size: $backupSizeMB MB"
    Write-Log "Compressed size: $compressedSizeMB MB"
    Write-Log "Current backups: $($currentBackups.Count)"
    Write-Log "Total backup size: $totalSizeMB MB"

    $notifyMsg = "Database: $PG_DB`nTime: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nFile: $(Split-Path $backupFileGz -Leaf)`nOriginal: $backupSizeMB MB`nCompressed: $compressedSizeMB MB`nBackups: $($currentBackups.Count)`nTotal: $totalSizeMB MB"
    Send-FeishuNotify -title "Database Backup Success" -message $notifyMsg -color "green"

    # 7. Write backup status file for Prometheus metrics sync
    #    Bridges the gap: this script does the actual pg_dump,
    #    but only the in-app backup service used to update metrics.
    $statusFile = "E:\AI\nuotao-ai-os\backups\last_backup_status.json"
    $status = @{
        timestamp = [int][double]::Parse((Get-Date -UFormat %s))
        timestamp_iso = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
        file_name = (Split-Path $backupFileGz -Leaf)
        file_path = $backupFileGz
        original_size_bytes = $backupSize
        compressed_size_bytes = $compressedSize
        success = $true
    } | ConvertTo-Json -Depth 5
    # Use .NET WriteAllText to avoid UTF-8 BOM (Python json.loads compatibility)
    [System.IO.File]::WriteAllText($statusFile, $status, [System.Text.UTF8Encoding]::new($false))
    Write-Log "Backup status file written: $statusFile"

} catch {
    Write-Log "Database backup failed: $_" "ERROR"
    Write-Log $_.ScriptStackTrace "ERROR"

    $notifyMsg = "Database: $PG_DB`nTime: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nError: $_`nLog: $logFile"
    Send-FeishuNotify -title "Database Backup Failed" -message $notifyMsg -color "red"

    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    exit 1
}

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
Write-Log "Backup script finished"
exit 0
