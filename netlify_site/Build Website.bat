@echo off
rem Rebuilds the public demo site from the FICTIONAL sample clients, then shows the zip to upload.
rem Upload: Netlify > tax-scan > Deploys > drag tax-scan-site.zip onto the page.
title Tax Scan - building website
cd /d "%~dp0..\app"
"..\.venv\Scripts\python.exe" scripts\build_netlify_demo.py
if errorlevel 1 ( pause & exit /b 1 )
explorer /select,"%~dp0tax-scan-site.zip"
pause
