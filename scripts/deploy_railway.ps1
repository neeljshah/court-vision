# deploy_railway.ps1 - one-shot Railway deploy for the live dashboard.
[CmdletBinding()]
param(
    [string]$ProjectName = "courtvision-live",
    [string]$GameId = "0042500315"
)

# Don't fail on stderr from native commands - we need to inspect exit codes.
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false
Set-Location $PSScriptRoot\..

function Run-Railway {
    param([string[]]$CmdArgs)
    $output = & railway @CmdArgs 2>&1 | Out-String
    return @{ ok = ($LASTEXITCODE -eq 0); output = $output.Trim() }
}

Write-Host "[1/6] Checking Railway auth..." -ForegroundColor Cyan
$r = Run-Railway -CmdArgs @("whoami")
if (-not $r.ok) {
    Write-Host "[error] not logged in. Run: railway login" -ForegroundColor Red
    exit 1
}
Write-Host "      $($r.output)" -ForegroundColor Green

Write-Host "[2/6] Checking if project already linked..." -ForegroundColor Cyan
$r = Run-Railway -CmdArgs @("status")
$needInit = (-not $r.ok) -or ($r.output -match "No linked project")
if ($needInit) {
    Write-Host "      no link - creating new project '$ProjectName'..." -ForegroundColor Yellow
    $r2 = Run-Railway -CmdArgs @("init", "--name", $ProjectName)
    if (-not $r2.ok) {
        Write-Host "[error] railway init failed:" -ForegroundColor Red
        Write-Host $r2.output -ForegroundColor Red
        exit 1
    }
    Write-Host "      created" -ForegroundColor Green
} else {
    Write-Host "      project already linked" -ForegroundColor Green
}

Write-Host "[3/6] Generating auth token if missing..." -ForegroundColor Cyan
$tokenFile = "$env:USERPROFILE\.cv_live_token"
if (-not (Test-Path $tokenFile)) {
    $token = python -c "import secrets; print(secrets.token_urlsafe(32))"
    $token = $token.Trim()
    Set-Content -Path $tokenFile -Value $token -Encoding ascii -NoNewline
    Write-Host "      new token saved to $tokenFile" -ForegroundColor Green
} else {
    $token = (Get-Content -Path $tokenFile -Raw).Trim()
    Write-Host "      reusing token from $tokenFile" -ForegroundColor Green
}

Write-Host "[4/6] Setting environment variables..." -ForegroundColor Cyan
$envPairs = @(
    "LIVE_V2_GAME_IDS=$GameId",
    "LIVE_V2_PBP_INTERVAL=15",
    "LIVE_V2_SNAPSHOT_INTERVAL=30",
    "LIVE_V2_LINEUP_INTERVAL=30",
    "LIVE_V2_LINE_INTERVAL=60",
    "LIVE_V2_ALLOWED_ORIGINS=*",
    "LIVE_V2_AUTH_TOKEN=$token",
    "PYTHONUNBUFFERED=1"
)
foreach ($pair in $envPairs) {
    $r = Run-Railway -CmdArgs @("variables", "--set", $pair)
    if (-not $r.ok) {
        Write-Host "[warn] variable set failed for $pair" -ForegroundColor Yellow
    }
}
Write-Host "      $($envPairs.Count) vars set" -ForegroundColor Green

Write-Host "[5/6] Uploading + deploying (this can take 3-5 min)..." -ForegroundColor Cyan
$r = Run-Railway -CmdArgs @("up", "--detach")
Write-Host $r.output
if (-not $r.ok) {
    Write-Host "[error] railway up failed" -ForegroundColor Red
    exit 1
}

Write-Host "[6/6] Generating public domain..." -ForegroundColor Cyan
$r = Run-Railway -CmdArgs @("domain")
Write-Host "      $($r.output)" -ForegroundColor Green

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host " Deploy complete." -ForegroundColor Magenta
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Token (append as ?token=...):  $token"
Write-Host "  Token saved file:              $tokenFile"
Write-Host "  Tail logs:                     railway logs"
Write-Host "  Variables:                     railway variables"
Write-Host "  Redeploy:                      railway up"
Write-Host ""
