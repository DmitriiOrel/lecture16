param(
    [string]$ProjectDir = "",
    [string]$PythonExe = "",
    [string]$StateJson = "",
    [string]$Config = "",
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

$pythonPrefixArgs = @()
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $ProjectDir = $scriptDir
}
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $venvPython = Join-Path $ProjectDir "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = "python"
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = "py"
        $pythonPrefixArgs = @("-3")
    } else {
        $PythonExe = "python"
    }
}
if ([string]::IsNullOrWhiteSpace($Config)) {
    $Config = Join-Path $ProjectDir "config\micro_near_v1_1m.json"
}
if ([string]::IsNullOrWhiteSpace($StateJson)) {
    $defaultState = Join-Path $ProjectDir "reports\kucoin_rl\latest_forecast_signal_kucoin_rl.json"
    $downloadsState = Join-Path $HOME "Downloads\latest_forecast_signal_kucoin_rl.json"
    if (Test-Path $defaultState) {
        $StateJson = $defaultState
    } elseif (Test-Path $downloadsState) {
        $StateJson = $downloadsState
    } else {
        $StateJson = $defaultState
    }
}

$runnerScript = Join-Path $ProjectDir "run_trade_signal.py"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $PythonExe) -and -not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "Python command not found: $PythonExe"
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

& $PythonExe @pythonPrefixArgs @args 2>&1 | Tee-Object -FilePath $logPath
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw "run_trade_signal.py finished with exit code $exitCode"
}

Write-Host "Done. ExitCode=0"
