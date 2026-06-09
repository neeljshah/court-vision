# setup_discord_webhook.ps1 — register a Discord webhook for Live Engine v2 alerts.
#
# Usage:
#     pwsh scripts/setup_discord_webhook.ps1 -WebhookUrl "https://discord.com/api/webhooks/.../..."
# Or (interactive):
#     pwsh scripts/setup_discord_webhook.ps1
#
# What it does:
#   1. Persists DISCORD_ALERT_WEBHOOK to your User environment block so
#      every new PowerShell / Python process sees it without --env flags.
#   2. Sends a sample alert through src/notifications/webhook_alerts.py
#      so you can confirm the webhook works before tipoff.
#
# How to obtain a webhook URL (one-time, ~30 seconds):
#   - Open your Discord server settings (gear icon next to the server name)
#   - Integrations → Webhooks → New Webhook
#   - Pick the channel where alerts should land
#   - Click "Copy Webhook URL"

[CmdletBinding()]
param(
    [string]$WebhookUrl,
    [switch]$SkipTest,
    [switch]$PrintOnly
)

$ErrorActionPreference = 'Stop'

function Read-WebhookInteractive {
    Write-Host "`nNo webhook URL passed; prompting interactively." -ForegroundColor Yellow
    Write-Host "Paste the full URL (https://discord.com/api/webhooks/...): " -NoNewline
    $url = Read-Host
    return $url.Trim()
}

if (-not $WebhookUrl) {
    $WebhookUrl = Read-WebhookInteractive
}

if (-not $WebhookUrl -or -not $WebhookUrl.StartsWith('https://discord.com/api/webhooks/')) {
    Write-Host "[error] expected a URL of the form https://discord.com/api/webhooks/..." -ForegroundColor Red
    exit 1
}

if ($PrintOnly) {
    Write-Host "[print-only] would set DISCORD_ALERT_WEBHOOK=$WebhookUrl" -ForegroundColor Yellow
    exit 0
}

Write-Host "[setup] writing DISCORD_ALERT_WEBHOOK to User environment block…"
[Environment]::SetEnvironmentVariable('DISCORD_ALERT_WEBHOOK', $WebhookUrl, 'User')
# Mirror into the current session so the test below picks it up immediately.
$env:DISCORD_ALERT_WEBHOOK = $WebhookUrl
Write-Host "[setup] OK — variable persists across reboots." -ForegroundColor Green

if ($SkipTest) {
    Write-Host "`n[skip-test] not sending a sample alert. Done."
    exit 0
}

Write-Host "`n[test] firing a sample alert via src/notifications/webhook_alerts.py…"

# Resolve repo root from this script's location.
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $repoRoot -or -not (Test-Path (Join-Path $repoRoot 'CLAUDE.md'))) {
    $repoRoot = (Get-Location).Path
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    Write-Host "[warn] no python on PATH; skipping test. Activate basketball_ai then rerun manually." -ForegroundColor Yellow
    exit 0
}

$pyScript = @"
import sys, os
sys.path.insert(0, r'$repoRoot')
from src.notifications.webhook_alerts import WebhookNotifier
n = WebhookNotifier(min_severity='info')
ok = n.send(
    'LIVE_ENGINE_V2_TEST',
    'Sample alert from setup_discord_webhook.ps1 — your channel is wired.',
    severity='high',
    tags={'source': 'setup_discord_webhook.ps1'},
)
print('webhook_ok' if ok else 'webhook_failed')
sys.exit(0 if ok else 1)
"@

$tmp = New-TemporaryFile
Set-Content -Path $tmp -Value $pyScript -Encoding utf8
try {
    & $python $tmp.FullName
    $code = $LASTEXITCODE
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

if ($code -eq 0) {
    Write-Host "`n[done] Discord webhook test alert sent — check your channel." -ForegroundColor Green
} else {
    Write-Host "`n[done] Webhook env var set but test alert failed — check that the URL is valid and the channel is reachable." -ForegroundColor Yellow
}
exit $code
