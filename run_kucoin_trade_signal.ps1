param(
    [string]$ProjectDir = "C:\projects\Work\work_project_1\lecture16",
    [string]$PythonExe = "C:\projects\Work\work_project_1\lecture16\venv\Scripts\python.exe",
    [string]$StateJson = "C:\projects\Work\work_project_1\lecture16\reports\kucoin_rl\latest_forecast_signal_kucoin_rl.json",
    [string]$Config = "C:\projects\Work\work_project_1\lecture16\config\micro_near_v1_1m.json",
    [switch]$RunRealOrder,
    [switch]$AllowShort,
    [ValidateSet("", "BUY", "SELL", "HOLD", "BUY_BOTH", "SELL_BOTH", "BUY_SPOT", "SELL_SPOT", "BUY_FUTURES", "SELL_FUTURES")]
    [string]$ForceAction = "",
    [double]$SpotQty = 0.1,
    [int]$FuturesContracts = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
cmd /c chcp 65001 > $null

$runnerScript = Join-Path $ProjectDir "run_trade_signal.py"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $PythonExe)) {
    throw "Python not found: $PythonExe"
}
if (-not (Test-Path $runnerScript)) {
    throw "Runner script not found: $runnerScript"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "kucoin_trade_signal_$timestamp.log"

$args = @(
    $runnerScript,
    "--state-json", $StateJson,
    "--config", $Config
)

if ($RunRealOrder) {
    $args += "--run-real-order"
} else {
    $args += @("--mode", "shadow")
}
if ($AllowShort) {
    $args += "--allow-short"
}
if (-not [string]::IsNullOrWhiteSpace($ForceAction)) {
    $args += @("--force-action", $ForceAction)
    $args += @("--spot-qty", $SpotQty)
    $args += @("--futures-contracts", $FuturesContracts)
}

Write-Host "Python       :" $PythonExe
Write-Host "Runner script:" $runnerScript
Write-Host "State JSON   :" $StateJson
Write-Host "Config       :" $Config
Write-Host "RunRealOrder :" $RunRealOrder.IsPresent
Write-Host "AllowShort   :" $AllowShort.IsPresent
Write-Host "ForceAction  :" $(if ($ForceAction) { $ForceAction } else { "<none>" })
if (-not [string]::IsNullOrWhiteSpace($ForceAction)) {
    Write-Host "SpotQty      :" $SpotQty
    Write-Host "FutContracts :" $FuturesContracts
}
Write-Host "Log file     :" $logPath

& $PythonExe @args 2>&1 | Tee-Object -FilePath $logPath
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw "run_trade_signal.py finished with exit code $exitCode"
}

Write-Host "Done. ExitCode=0"
