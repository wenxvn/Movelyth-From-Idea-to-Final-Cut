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
    & '.\.venv\Scripts\python.exe' -m movelyth doctor
    if ($LASTEXITCODE -ne 0) { throw '运行环境检查未通过，见上方具体缺项' }
} finally {
    Pop-Location
}
