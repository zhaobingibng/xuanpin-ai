@echo off
chcp 65001 >nul
title XuanPin AI 每日采集
cd /d "%~dp0"

echo ============================================
echo    XuanPin AI  每日选品任务
echo ============================================
echo.

REM ---- 环境检测：优先 conda 环境 xuanpin-ai，其次项目自带 .venv ----
REM  PYEXE = 实际使用的 python 可执行文件（.venv 用完整路径，避免误用系统 python）
set "PYEXE="
where conda >nul 2>nul
if %ERRORLEVEL%==0 (
    call conda activate xuanpin-ai
    set "PYEXE=python"
    goto :run
)
if exist ".venv\Scripts\python.exe" (
    call .venv\Scripts\activate.bat
    set "PYEXE=%~dp0.venv\Scripts\python.exe"
    goto :run
)
echo [错误] 未找到 conda 环境 xuanpin-ai，也未找到项目 .venv 虚拟环境。
echo        请先创建 conda 环境，或在项目根目录执行 "uv sync" 生成 .venv。
echo.
pause
exit /b 1

:run
echo [执行] %PYEXE% -m app.cli daily
echo        （采集 -> 入库评分 -> 推荐池 -> 供应链匹配 -> 日报）
echo.
"%PYEXE%" -m app.cli daily
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [失败] 每日任务执行出错，退出码 %ERRORLEVEL%。
    echo        请查看 logs\app.log 与 logs\error.log 排查。
    echo.
    pause
    exit /b 1
)

echo.
echo [完成] 每日任务执行结束。
echo.
pause
