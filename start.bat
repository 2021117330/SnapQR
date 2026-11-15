@echo off
rem 双击启动 SnapQR（优先使用项目自带的 .venv）
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m snapqr %*
    exit /b 0
)

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe -m snapqr %*
    exit /b 0
)

echo 没有找到 Python。请先安装 Python 3.10+，或运行 build.ps1 打包 exe。
pause
