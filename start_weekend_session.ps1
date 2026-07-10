# Weekend SAFETY MONITOR launcher (Pro account) -- restart-on-crash wrapper.
# The real worker runs in the desktop app on the Max account
# (.planning/WEEKEND_SESSION_PROMPT.md). This window only monitors.
# Rerun anytime: powershell -ExecutionPolicy Bypass -File start_weekend_session.ps1
Set-Location "C:\Users\neelj\nba-ai-system"
while ($true) {
    claude --remote-control "read .planning/MONITOR_SESSION_PROMPT.md and execute it"
    Write-Host "monitor exited -- relaunching in 5s (Ctrl+C to stop)"
    Start-Sleep 5
}
