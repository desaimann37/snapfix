@echo off
cd /d "%~dp0"
docker compose down
echo SnapFix stopped. Your data is kept; start.cmd brings it back.
pause
