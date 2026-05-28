@echo off
REM 边拆边审改造的端到端冒烟脚本
REM 用法（PowerShell 或 cmd）：双击运行，或 `verify_interleaved_audit.bat`

REM 1. 杀掉所有残留 web_main / spawn_main 进程（含父子 worker）
echo === 1. 杀掉所有残留 web_main 进程 ===
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*web_main*' -or $_.CommandLine -like '*spawn_main*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('  killed ' + $_.ProcessId) }"

REM 2. 等 1 秒让 socket 释放
timeout /t 1 /nobreak >nul

REM 3. 后端 AST + 实例化 + 抽象方法校验
echo.
echo === 2. 后端语法/导入/实例化校验 ===
py -3.10 -c "import ast; [ast.parse(open(p,encoding='utf-8').read()) for p in ['agents/plotter.py','core/pipeline.py','agents/outline_global_checker.py','agents/outline_auditor.py','agents/capability_extractor.py']]; print('ast ok')"
if errorlevel 1 goto :fail

py -3.10 -c "from core.pipeline import NovelPipeline; p=NovelPipeline(); assert hasattr(p,'_audit_one_batch') and hasattr(p,'_finalize_outline_audit') and not hasattr(p,'_run_outline_audit'); print('pipeline ok: _audit_one_batch + _finalize_outline_audit present')"
if errorlevel 1 goto :fail

REM 4. 前端构建
echo.
echo === 3. 前端 npm run build ===
pushd frontend
call npm run build
if errorlevel 1 (popd & goto :fail)
popd

REM 5. 后端启动
echo.
echo === 4. 启动后端（py -3.10 web_main.py）===
echo 后端日志会输出到当前窗口。请打开 http://localhost:8000 实测。
echo 关闭此窗口或 Ctrl+C 停止后端。
py -3.10 web_main.py
goto :eof

:fail
echo.
echo === 验证失败，请检查上方输出 ===
exit /b 1
