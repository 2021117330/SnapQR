#requires -Version 5.1
<#
.SYNOPSIS
    一键打包 SnapQR 为单文件 exe。

.DESCRIPTION
    - 自动创建 .venv 并安装依赖（可用 -SkipInstall 跳过）
    - 使用 PyInstaller + SnapQR.spec 生成 dist\SnapQR.exe
    - 国内网络慢时可以指定 -IndexUrl 使用镜像

.EXAMPLE
    .\build.ps1
    .\build.ps1 -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
#>
param(
    [switch]$SkipInstall,
    [string]$IndexUrl = ""
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    $venvPython = ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }

    $launchers = @(
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )
    foreach ($launcher in $launchers) {
        if (-not (Get-Command $launcher.Exe -ErrorAction SilentlyContinue)) { continue }
        Write-Host "尝试用 $($launcher.Exe) 创建虚拟环境 ..."
        try {
            & $launcher.Exe @($launcher.Args) -m venv .venv
        } catch {
            Write-Host "  $($launcher.Exe) 不可用：$($_.Exception.Message)"
        }
        if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPython)) {
            return (Resolve-Path $venvPython).Path
        }
        if (Test-Path ".venv") {
            Remove-Item ".venv" -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    throw "没有找到 Python 3.10+，请先安装：https://www.python.org/downloads/windows/"
}

$python = Find-Python
Write-Host "使用 Python: $python"

if (-not $SkipInstall) {
    $pipArgs = @("install", "--upgrade", "pip")
    if ($IndexUrl) { $pipArgs += @("-i", $IndexUrl) }
    & $python -m pip @pipArgs
    $pipArgs = @("install", "-r", "requirements-dev.txt")
    if ($IndexUrl) { $pipArgs += @("-i", $IndexUrl) }
    & $python -m pip @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }
}

& $python -m PyInstaller --noconfirm --clean SnapQR.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$exe = Join-Path $PSScriptRoot "dist\SnapQR.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "打包完成：$exe ($size MB)" -ForegroundColor Green
} else {
    throw "没有找到 dist\SnapQR.exe"
}
