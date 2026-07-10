# Weekend worker launcher -- restart-on-crash wrapper for the remote-controlled session.
# Rerun anytime with: powershell -ExecutionPolicy Bypass -File start_weekend_session.ps1
Set-Location "C:\Users\neelj\nba-ai-system"
while ($true) {
    claude --remote-control "read .planning/WEEKEND_SESSION_PROMPT.md and execute it"
    Write-Host "session exited -- relaunching in 5s (Ctrl+C to stop)"
    Start-Sleep 5
}
