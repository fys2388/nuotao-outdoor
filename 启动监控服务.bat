@echo off
REM ============================================
REM Nuotao AI OS - 监控服务启动脚本 (Windows)
REM ============================================
REM 功能：后台启动系统监控与告警服务
REM 使用方法：双击运行，或命令行执行
REM ============================================

echo ============================================
echo   Nuotao AI OS - 监控服务启动
echo ============================================
echo.

cd /d E:\AI\nuotao-ai-os\backend

REM 检查 Python 虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python 虚拟环境不存在: .venv\Scripts\python.exe
    pause
    exit /b 1
)

REM 检查监控脚本
if not exist "E:\AI\nuotao-ai-os\scripts\monitor_service.py" (
    echo [ERROR] 监控脚本不存在: scripts\monitor_service.py
    pause
    exit /b 1
)

echo [INFO] 启动监控服务...
echo [INFO] 日志目录: E:\AI\nuotao-ai-os\backups\monitoring
echo [INFO] 检查间隔: 60 秒
echo.

REM 后台启动监控服务
start "Nuotao Monitor" /min ".venv\Scripts\python.exe" "E:\AI\nuotao-ai-os\scripts\monitor_service.py"

echo [SUCCESS] 监控服务已在后台启动
echo [INFO] 窗口标题: Nuotao Monitor
echo [INFO] 可以通过任务管理器查看进程
echo.
echo 按任意键退出...
pause >nul
