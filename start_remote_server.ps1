# Remote Control SERVER (Max account) -- the dispatch target for the phone.
# Hosts sessions started from the Claude mobile app (Code tab -> this machine).
# Crash-safe: relaunches in 5s. Rerun anytime:
#   powershell -ExecutionPolicy Bypass -File start_remote_server.ps1
Set-Location "C:\Users\neelj\nba-ai-system"
while ($true) {
    claude remote-control
    Write-Host "remote-control server exited -- relaunching in 5s (Ctrl+C to stop)"
    Start-Sleep 5
}
