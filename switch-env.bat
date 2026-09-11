@echo off
chcp 65001 >nul
REM ============================================
REM Nuotao AI OS - 环境切换脚本 (Windows)
REM 用法: switch-env.bat [dev|staging|prod]
REM ============================================

setlocal enabledelayedexpansion

set "ENV=%~1"
set "BACKEND_DIR=E:\AI\nuotao-ai-os\backend"
set "ENV_FILE=%BACKEND_DIR%\.env"

if "%ENV%"=="" (
    echo 当前环境:
    if exist "%ENV_FILE%" (
        findstr /C:"ENVIRONMENT=" "%ENV_FILE%"
    ) else (
        echo   未配置 (.env 文件不存在)
    )
    echo.
    echo 用法: switch-env.bat [dev^|staging^|prod]
    echo   dev     - 开发环境 (本地调试)
    echo   staging - 预发布环境 (UAT测试)
    echo   prod    - 生产环境 (正式上线)
    exit /b 0
)

if /i "%ENV%"=="dev" (
    set "SOURCE_FILE=%BACKEND_DIR%\.env.development"
    set "ENV_NAME=开发环境 (Development)"
) else if /i "%ENV%"=="staging" (
    set "SOURCE_FILE=%BACKEND_DIR%\.env.staging"
    set "ENV_NAME=预发布环境 (Staging)"
) else if /i "%ENV%"=="prod" (
    set "SOURCE_FILE=%BACKEND_DIR%\.env.production"
    set "ENV_NAME=生产环境 (Production)"
) else (
    echo [错误] 未知环境: %ENV%
    echo 可选: dev, staging, prod
    exit /b 1
)

if not exist "%SOURCE_FILE%" (
    echo [错误] 配置文件不存在: %SOURCE_FILE%
    exit /b 1
)

echo ============================================
echo  Nuotao AI OS - 环境切换
echo ============================================
echo.
echo 目标环境: %ENV_NAME%
echo 源文件:   %SOURCE_FILE%
echo 目标文件: %ENV_FILE%
echo.

if /i "%ENV%"=="prod" (
    echo [警告] 即将切换到生产环境！
    echo [警告] 请确认所有密钥已正确配置！
    choice /C YN /M "确认切换到生产环境"
    if errorlevel 2 (
        echo 已取消
        exit /b 0
    )
)

copy /Y "%SOURCE_FILE%" "%ENV_FILE%" >nul

echo.
echo [成功] 已切换到 %ENV_NAME%
echo.
echo 当前配置摘要:
findstr /C:"ENVIRONMENT=" /C:"DEBUG=" /C:"LOG_LEVEL=" /C:"DATABASE_URL=" "%ENV_FILE%"
echo.
echo ============================================
echo  注意: 切换环境后需要重启后端服务
echo  命令: 停止 Nuotao AI OS.bat ^&^& 启动 Nuotao AI OS.bat
echo ============================================

endlocal
