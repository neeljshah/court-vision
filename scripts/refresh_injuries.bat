@echo off
REM CourtVision same-day freshness — refresh tonight's NBA injury feed.
REM Writes data/cache/nba_injuries_<today>.parquet (the file the gated vac-bump reads).
REM Does NOT touch golive or the live :8077 server. Safe to run on a schedule.
REM Registered as scheduled task "CourtVision Injury Refresh" (every 2h). Logs append below.
cd /d C:\Users\neelj\nba-ai-system
set PYTHONIOENCODING=utf-8
echo [%date% %time%] refreshing injury feed... >> data\cache\_injury_refresh.log
C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe scripts\nba_injury_report_scraper.py >> data\cache\_injury_refresh.log 2>&1
echo [%date% %time%] done (exit %errorlevel%). >> data\cache\_injury_refresh.log
