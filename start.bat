@echo off
REM Windows: double-click to start Youtube Card Reader.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start.ps1"
pause
