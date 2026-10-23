@echo off
rem Double-click to start the Tax Return Grader. Your browser opens to the upload page.
rem Keep this window open while you use it; close it to stop the grader.
title Tax Return Grader
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The grader isn't set up on this computer yet. See README.md, section 1 "Setup".
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m src.webapp
if errorlevel 1 pause
