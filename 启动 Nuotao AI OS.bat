@echo off
chcp 65001 >nul
title Nuotao AI OS 一键启动

echo ========================================
echo   Nuotao AI OS 一键启动脚本
echo ========================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [提示] 建议以管理员身份运行此脚本
    echo.
)

:: 启动 PostgreSQL
echo [1/4] 启动 PostgreSQL...
net start postgresql-x64-17 2>nul
if %errorLevel% equ 0 (
    echo   ✅ PostgreSQL 已启动
) else (
    echo   ⚠️  PostgreSQL 可能已在运行或启动失败
)
timeout /t 2 /nobreak >nul

:: 启动 Redis
echo [2/4] 启动 Redis...
tasklist /fi "imagename eq redis-server.exe" 2>nul | findstr /i "redis-server.exe" >nul
if %errorLevel% equ 0 (
    echo   ✅ Redis 已在运行
) else (
    start "Redis" /min cmd /c "cd /d E:\AI\redis5 && redis-server.exe redis.windows.conf"
    echo   ✅ Redis 已启动
)
timeout /t 2 /nobreak >nul

:: 启动后端
echo [3/4] 启动后端服务 (端口 8000)...
tasklist /fi "imagename eq python.exe" 2>nul | findstr /i "python.exe" >nul
if %errorLevel% equ 0 (
    echo   ⚠️  检测到 Python 进程，可能后端已在运行
) else (
    start "Nuotao Backend" /min cmd /c "cd /d E:\AI\nuotao-ai-os\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo   ✅ 后端服务已启动
)
timeout /t 5 /nobreak >nul

:: 启动前端
echo [4/4] 启动前端管理控制台 (端口 3000)...
tasklist /fi "imagename eq node.exe" 2>nul | findstr /i "node.exe" >nul
if %errorLevel% equ 0 (
    echo   ⚠️  检测到 Node 进程，可能前端已在运行
) else (
    start "Nuotao Frontend" /min cmd /c "cd /d E:\AI\nuotao-ai-os\frontend && npm run dev"
    echo   ✅ 前端服务已启动
)
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   ✅ 所有服务启动完成！
echo ========================================
echo.
echo   【重要】访问地址（请复制到浏览器）：
echo.
echo   🖥️  管理控制台: http://localhost:3000
echo   📖 API 文档:   http://localhost:8000/docs
echo.
echo   注意：不要直接访问 http://localhost（端口80没有服务）
echo.
echo   按任意键打开管理控制台...
pause >nul

start "" "http://localhost:3000"

echo.
echo   已在浏览器中打开管理控制台
echo   此窗口可以最小化，不要关闭（关闭会停止服务）
echo.
pause
