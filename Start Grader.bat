@echo off
rem Double-click to open Tax Scan in your browser. Drag client folders onto the page to grade them.
rem Keep this window open while you use it; close it to stop.
title Tax Scan
cd /d "%~dp0app"
if not exist "..\.venv\Scripts\python.exe" (
  echo Tax Scan isn't set up on this computer yet. See README.md, section 1 "Setup".
  pause
  exit /b 1
)
"..\.venv\Scripts\python.exe" -m src.webapp
if errorlevel 1 pause
