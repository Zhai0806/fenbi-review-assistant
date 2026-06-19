@echo off
echo ========================================
echo   粉笔模考复盘助手 - 一键启动
echo ========================================
echo.
echo 启动后端 (FastAPI :8000) ...
start "后端" cmd /k "cd /d %~dp0 && uvicorn backend.main:app --port 8000 --reload"

echo 启动前端 (React :5173) ...
start "前端" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo 后端: http://localhost:8000
echo 前端: http://localhost:5173
echo.
echo 两个窗口已打开。关闭任一窗口即可停止对应服务。
pause
