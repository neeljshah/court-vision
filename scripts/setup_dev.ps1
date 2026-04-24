# CourtVision - dev environment setup for Windows PowerShell
# Run: powershell -ExecutionPolicy Bypass -File scripts/setup_dev.ps1
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "=== CourtVision Dev Setup ===" -ForegroundColor Cyan
Write-Host "Repo: $(Get-Location)"

if (-not (Test-Path "requirements.txt")) {
    Write-Error "requirements.txt not found. Run from repo root."
    exit 1
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda not found. Install Miniconda: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
}

$envs = conda env list | Out-String
if ($envs -match "basketball_ai") {
    Write-Host "[1/5] conda env 'basketball_ai' exists - reusing"
} else {
    Write-Host "[1/5] Creating conda env 'basketball_ai' (Python 3.9)..."
    conda create -n basketball_ai python=3.9 -y
}

Write-Host "[2/5] Installing Python dependencies..."
conda run -n basketball_ai --no-capture-output pip install -r requirements.txt

if (-not (Test-Path "yolov8n.pt")) {
    Write-Host "[3/5] Downloading yolov8n.pt..."
    conda run -n basketball_ai --no-capture-output python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
}
if (-not (Test-Path "yolov8n-pose.pt")) {
    Write-Host "[3/5] Downloading yolov8n-pose.pt..."
    conda run -n basketball_ai --no-capture-output python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
}

if (-not (Test-Path ".env")) {
    Write-Host "[4/5] Creating .env from .env.example - FILL IN API KEYS"
    Copy-Item ".env.example" ".env"
} else {
    Write-Host "[4/5] .env exists - skipping"
}

New-Item -ItemType Directory -Force -Path data/tracking, data/games, data/videos/full_games, logs, data/output, data/predictions | Out-Null

Write-Host "[5/5] Verifying prop models load..."
conda run -n basketball_ai --no-capture-output python -c "import sys; sys.path.insert(0, '.'); from src.prediction.prop_model_stack import PropModelStack; s = PropModelStack(); s.load_models(); print('  Prop models loaded:', sorted(s.models.keys()))"

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "  Activate:  conda activate basketball_ai"
Write-Host "  Tests:     python -m pytest tests/ -q"
Write-Host "  API:       uvicorn api.main:app --reload"
Write-Host "  .env keys: NBA_API_KEY, THE_ODDS_API_KEY, CLAUDE_API_KEY, DATABASE_URL"
