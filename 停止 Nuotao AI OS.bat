@echo off
chcp 65001 >nul
title Nuotao AI OS 停止服务

echo ========================================
echo   Nuotao AI OS 停止服务脚本
echo ========================================
echo.

echo [1/4] 停止前端服务...
taskkill /f /im node.exe 2>nul
echo   ✅ 前端服务已停止

echo [2/4] 停止后端服务...
taskkill /f /im python.exe 2>nul
echo   ✅ 后端服务已停止

echo [3/4] 停止 Redis...
taskkill /f /im redis-server.exe 2>nul
echo   ✅ Redis 已停止

echo [4/4] 停止 PostgreSQL...
net stop postgresql-x64-17 2>nul
echo   ✅ PostgreSQL 已停止

echo.
echo ========================================
echo   ✅ 所有服务已停止
echo ========================================
echo.
pause
