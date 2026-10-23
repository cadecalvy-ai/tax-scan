@echo off
rem Grades every client folder in inputs\clients and opens the ranking.
rem Each client needs inputs\clients\<Client>\client.yaml with  consent_7216: true  (see inputs\clients\README.txt).
title Tax Scan - grading inputs\clients
cd /d "%~dp0app"
if not exist "..\.venv\Scripts\python.exe" (
  echo Tax Scan isn't set up on this computer yet. See README.md, section 1 "Setup".
  pause
  exit /b 1
)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set RUN=%%i
set OUT=..\outputs\clients_%RUN%
"..\.venv\Scripts\python.exe" -m src.grader ..\inputs\clients --out "%OUT%" --workers 4
if errorlevel 1 ( pause & exit /b 1 )
start "" "%OUT%\summary.html"
echo.
echo Reports saved in outputs\clients_%RUN%
pause
