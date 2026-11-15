@echo off
rem 一键打包（绕过 PowerShell 执行策略限制）
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
    echo.
    echo 打包失败，请查看上面的错误信息。
    pause
)
