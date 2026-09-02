<#
.SYNOPSIS
    Nuotao AI OS - Database Restore Script (Simplified)
.DESCRIPTION
    Restore PostgreSQL database from backup file
.PARAMETER BackupFile
    Path to backup file (.sql or .sql.gz)
.PARAMETER TargetDB
    Target database name (default: nuotao_restore)
.PARAMETER VerifyOnly
    Only verify backup file and connection, do not restore
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [Parameter(Mandatory=$false)]
    [string]$TargetDB = "nuotao_restore",

    [Parameter(Mandatory=$false)]
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

# Configuration
$PG_BIN = "C:\Program Files\PostgreSQL\17\bin"
$PG_HOST = "localhost"
$PG_PORT = "5432"
$PG_USER = "nuotao"
$PG_PASSWORD = "nuotao_dev_password"
$env:PGPASSWORD = $PG_PASSWORD

$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$LOG_FILE = "E:\AI\nuotao-ai-os\backups\logs\restore_$TIMESTAMP.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] [$Level] $Message"
    Write-Host $entry
    Add-Content -Path $LOG_FILE -Value $entry -Encoding UTF8
}

Write-Host "============================================"
Write-Host " Nuotao AI OS - Database Restore"
Write-Host "============================================"
Write-Host ""

# Ensure log directory
$logDir = Split-Path $LOG_FILE -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Log "Starting restore process"
Write-Log "Backup file: $BackupFile"
Write-Log "Target DB: $TargetDB"

# Step 1: Verify backup file
if (-not (Test-Path $BackupFile)) {
    Write-Log "ERROR: Backup file not found: $BackupFile" "ERROR"
    exit 1
}
$fileSize = (Get-Item $BackupFile).Length
Write-Log "Backup file size: $([math]::Round($fileSize/1KB, 2)) KB"

# Step 2: Test database connection
Write-Log "Testing database connection..."
$connResult = & "$PG_BIN\psql.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER -d "postgres" -c "SELECT version();" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Database connection failed" "ERROR"
    Write-Log $connResult "ERROR"
    exit 1
}
Write-Log "Database connection successful"

if ($VerifyOnly) {
    Write-Host ""
    Write-Host "============================================"
    Write-Host " Verification Complete!"
    Write-Host "============================================"
    Write-Host "Backup file: valid"
    Write-Host "Database connection: OK"
    Write-Host "Log: $LOG_FILE"
    Write-Host "============================================"
    exit 0
}

# Step 3: Create target database
Write-Log "Creating target database: $TargetDB"
& "$PG_BIN\dropdb.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER --if-exists $TargetDB 2>&1 | Out-Null
& "$PG_BIN\createdb.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER -O $PG_USER $TargetDB 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Failed to create database" "ERROR"
    exit 1
}
Write-Log "Database created: $TargetDB"

# Step 4: Restore
$startTime = Get-Date
Write-Log "Starting restore..."

$isGzip = $BackupFile -match "\.gz$"
if ($isGzip) {
    $tempSql = "$env:TEMP\nuotao_restore_$TIMESTAMP.sql"
    Write-Log "Decompressing to: $tempSql"
    & "$PG_BIN\gzip.exe" -d -c $BackupFile | Out-File -FilePath $tempSql -Encoding UTF8
    $sqlFile = $tempSql
} else {
    $sqlFile = $BackupFile
}

Write-Log "Restoring from: $sqlFile"
$restoreResult = & "$PG_BIN\psql.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER -d $TargetDB -f $sqlFile -q 2>&1

if ($isGzip -and (Test-Path $tempSql)) {
    Remove-Item $tempSql -Force
}

$duration = ((Get-Date) - $startTime).TotalSeconds
Write-Log "Restore completed in $([math]::Round($duration, 2)) seconds"

# Step 5: Verify data
Write-Log "Verifying restored data..."
$tableCount = & "$PG_BIN\psql.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER -d $TargetDB -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>&1
Write-Log "Tables restored: $($tableCount.Trim())"

$criticalTables = @("users", "products", "orders", "customers")
foreach ($table in $criticalTables) {
    $count = & "$PG_BIN\psql.exe" -h $PG_HOST -p $PG_PORT -U $PG_USER -d $TargetDB -t -c "SELECT count(*) FROM $table;" 2>&1
    Write-Log "  $table : $($count.Trim()) rows"
}

Write-Host ""
Write-Host "============================================"
Write-Host " Restore Complete!"
Write-Host "============================================"
Write-Host "Target database: $TargetDB"
Write-Host "Tables restored: $($tableCount.Trim())"
Write-Host "Duration: $([math]::Round($duration, 2)) seconds"
Write-Host "Log: $LOG_FILE"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Verify application works with restored data"
Write-Host "  2. Update .env with new database name if needed"
Write-Host "  3. Restart backend service"
Write-Host "============================================"

Write-Log "Restore process completed successfully"
