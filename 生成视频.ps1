param(
    [Parameter(Position=0)][string]$Title,
    [string]$Brief,
    [switch]$New,
    [switch]$Preview,
    [switch]$PlanOnly
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
if (-not [string]::IsNullOrWhiteSpace($Brief)) { $cliArgs += @('--brief-file', $Brief) }
if ($New) { $cliArgs += '--new' }
if ($Preview) { $cliArgs += '--preview' }
if ($PlanOnly) { $cliArgs += '--plan-only' }
& $pythonExe @cliArgs
exit $LASTEXITCODE
