# stop.ps1 -- ONE-COMMAND "STOP".
# Cleanly drains the supervisor and every child service. Safe to run any time.
# Self-improve stays ARMED for next time; delete data\cache\improve\PIPELINE_ENABLED
# if you want to disarm learning entirely.

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ROOT

Write-Output "STOP | draining the supervised stack..."
& (Join-Path $ROOT "boot.ps1") -Stop
Write-Output "STOP | done. The system is fully stopped."
Write-Output "STOP | (self-improve stays armed; restart any time with .\go.ps1)"
