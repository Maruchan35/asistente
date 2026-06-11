@echo off
title JARVIS Watchdog
cd /d "%~dp0"

:: Lanzar JARVIS bajo supervision: si crashea, se relanza solo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" watchdog.py
) else (
    python watchdog.py
)
pause
