param(
    [Parameter(Position=0)][string]$Title,
    [switch]$New
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw '请先执行 setup.ps1 创建项目运行环境。'
}
if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = Read-Host '请输入本期视频标题'
}
$cliArgs = @('-m', 'movelyth', '--root', $projectRoot, 'create', $Title)
if ($New) { $cliArgs += '--new' }
& $pythonExe @cliArgs
exit $LASTEXITCODE
