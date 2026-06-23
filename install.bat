@echo off
setlocal
REM Windows double-click installer for marketplace-mcp.
cd /d "%~dp0"

REM --- Step 0: make sure Python 3.10+ exists. Prefer the py launcher, ---
REM --- fall back to python on PATH. ---
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)

REM --- Pre-install step: if Python is missing, try winget (built into ---
REM --- Windows 10/11). Zero-engineer path: no manual download. ---
if not defined PYEXE (
  where winget >nul 2>nul && (
    echo.
    echo Python 3.10+ was not found. Installing it now via winget...
    echo A Windows prompt may ask for permission - click Yes.
    echo.
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    REM winget updates PATH only for new shells, so re-detect via the launcher.
    where py >nul 2>nul && set "PYEXE=py -3"
    if not defined PYEXE (
      where python >nul 2>nul && set "PYEXE=python"
    )
  )
)

REM --- Still nothing? Hand the user the manual path. ---
if not defined PYEXE (
  echo.
  echo Python 3.10+ was not found and could not be installed automatically.
  echo Install it from https://python.org and tick "Add python.exe to PATH",
  echo then double-click this file again.
  echo.
  echo If you just installed Python via winget, simply close this window
  echo and double-click install.bat again ^(PATH refreshes for new windows^).
  echo.
  pause
  exit /b 1
)

REM --- Step 1: run the cross-platform installer. ---
%PYEXE% install.py %*
echo.
echo If you entered keys, you can verify with:
echo    %PYEXE% serve.py ozon --selfcheck
echo.
pause
endlocal
