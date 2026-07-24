@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ==========================================================
REM  子窗口分发：backend / frontend 由主流程用 start 重新调用本脚本
REM ==========================================================
if /I "%~1"=="backend"  goto :backend
if /I "%~1"=="frontend" goto :frontend

REM ================= 主流程 =================
title XuanPin AI 一键启动
echo ============================================
echo    XuanPin AI  本地一键启动
echo ============================================
echo.

REM ---- 预检环境（失败则直接退出，避免弹出无用窗口）----
call :detect_env
if errorlevel 1 (
    echo [错误] 未找到 conda 环境 xuanpin-ai，也未找到项目 .venv 虚拟环境。
    echo        请先创建 conda 环境，或在项目根目录执行 "uv sync" 生成 .venv。
    echo.
    pause
    exit /b 1
)
echo [环境] 激活方式: %ACT%
echo.

echo [1/3] 启动 FastAPI 后端  ->  http://127.0.0.1:8000
start "XuanPin 后端 - FastAPI" cmd /k ""%~f0" backend"

echo [2/3] 启动 Vue Dashboard  ->  http://localhost:5173
start "XuanPin 前端 - Vue" cmd /k ""%~f0" frontend"

echo [3/3] 等待服务就绪，随后自动打开浏览器 ...
timeout /t 8 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo ============================================
echo   启动完成
echo   后端 API : http://127.0.0.1:8000
echo   前端页面 : http://localhost:5173
echo   关闭对应的两个 cmd 窗口即可停止服务。
echo ============================================
echo.
pause
exit /b 0

REM ================= 环境检测子程序 =================
REM  优先 conda 环境 xuanpin-ai，其次项目自带 .venv
REM  ACT   = 激活命令（conda 场景需要）
REM  PYEXE = 实际使用的 python 可执行文件（.venv 用完整路径，避免误用系统 python）
:detect_env
set "ACT="
set "PYEXE="
where conda >nul 2>nul
if %errorlevel%==0 (
    set "ACT=call conda activate xuanpin-ai"
    set "PYEXE=python"
    exit /b 0
)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "ACT=call .venv\Scripts\activate.bat"
    set "PYEXE=%~dp0.venv\Scripts\python.exe"
    exit /b 0
)
exit /b 1

REM ================= 后端子窗口 =================
:backend
title XuanPin 后端 - FastAPI
cd /d "%~dp0"
call :detect_env
if errorlevel 1 (
    echo [后端启动失败] 未找到 Python 环境（conda xuanpin-ai 或 .venv）。
    pause
    exit /b 1
)
echo [后端] 激活环境: %ACT%
%ACT%
echo [后端] 使用解释器: %PYEXE%
echo [后端] 启动 uvicorn app.api.main:app （端口 8000）...
"%PYEXE%" -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
echo.
echo [后端已停止或启动失败] 退出码 %errorlevel%，请检查依赖安装与 8000 端口占用。
pause
exit /b

REM ================= 前端子窗口 =================
:frontend
title XuanPin 前端 - Vue
cd /d "%~dp0xuanpin-dashboard"
if not exist "node_modules" (
    echo [前端] 首次运行，安装依赖 npm install（较慢，请耐心等待）...
    call npm install
)
echo [前端] 启动 npm run dev （端口 5173）...
call npm run dev
echo.
echo [前端已停止或启动失败] 退出码 %errorlevel%，请确认已安装 Node.js。
pause
exit /b
