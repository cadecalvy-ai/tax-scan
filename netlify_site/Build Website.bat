@echo off
rem Rebuilds the public demo site from the FICTIONAL sample clients and publishes it to tax-scan.netlify.app.
rem Publishing needs the Netlify tool signed in on this PC (it is linked to the tax-scan site).
rem If it isn't, the zip is shown instead: Netlify > tax-scan > Deploys > drag tax-scan-site.zip onto the page.
title Tax Scan - building website
cd /d "%~dp0..\app"
"..\.venv\Scripts\python.exe" scripts\build_netlify_demo.py
if errorlevel 1 ( pause & exit /b 1 )
cd /d "%~dp0.."
set "PATH=%PATH%;%APPDATA%\npm;%ProgramFiles%\nodejs"
where netlify >nul 2>nul
if errorlevel 1 goto manual
if not exist ".netlify\state.json" goto manual
echo.
echo Publishing to tax-scan.netlify.app ...
call netlify deploy --prod --dir "netlify_site/site" --message "Build Website.bat"
if errorlevel 1 goto manual
echo.
echo Done: https://tax-scan.netlify.app
pause
exit /b 0

:manual
echo.
echo Couldn't publish automatically. Upload the zip by hand (File Explorer is opening on it).
explorer /select,"%~dp0tax-scan-site.zip"
pause
