@echo off
REM Windows double-click installer.
cd /d "%~dp0"
where py >nul 2>nul && (py install.py %* & goto end)
where python >nul 2>nul && (python install.py %* & goto end)
echo Python 3.10+ not found. Install it from https://python.org (tick "Add to PATH"), then run again.
pause
:end
pause
