$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '创建 Python 环境失败' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw '安装 Python 依赖失败' }
    npm.cmd --prefix studio ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw '安装视频依赖失败' }
    # doctor 以非零退出表示"还不能真实生成"（通常是没配模型端点），
    # 这不该让环境安装失败：把报告打出来，由使用者决定下一步。
    & '.\.venv\Scripts\python.exe' -m movelyth doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '环境已安装，但还不能真实生成：见上方 reasons。' -ForegroundColor Yellow
        Write-Host '配置模型端点（或 codex login）后运行 .\生成视频.ps1 即可。' -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}
