@echo off
REM Ensure the footage-bridge lane workers are running. SHORT-LIVED by design.
REM
REM WHY NOT bridge_supervisor: on 2026-09-02 every long-lived supervisor died
REM silently inside main() within minutes under four different launch methods
REM (nohup, PowerShell Start-Process, Task Scheduler, agent background runner),
REM with no Python exception -- a BaseException handler around main() printed
REM nothing. Not the task policy (IgnoreNew, PT72H) and not memory (3.83 GB free,
REM largest python 56 MB). Cause never identified. But the lane workers were
REM repeatedly observed SURVIVING their parent, so bridge_keeper starts them
REM detached and exits, leaving nothing long-lived to die.
REM
REM bridge_keeper is idempotent: a run while all seven lanes are healthy starts
REM nothing. That is what prevents the worker accumulation seen earlier, when a
REM blocked heartbeat made a healthy supervisor look dead and a second one was
REM started alongside it.
cd /d C:\Users\neelj\nba-ai-system
python -m scripts.platformkit.bridge_keeper --per-lane 1 >> logs\bridge_watchdog.log 2>&1
