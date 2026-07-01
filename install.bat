@echo off
setlocal
REM Windows double-click installer for marketplace-mcp.
cd /d "%~dp0"

REM --- Step 0: find a REAL Python 3.10+. Prefer the py launcher, fall back ---
REM --- to python on PATH. Every candidate must pass a version check: the  ---
REM --- WindowsApps "python" stub (opens the Store) and old Pythons fail   ---
REM --- it and are treated as missing.                                     ---
call :detect

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
    call :detect
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
echo    %PYEXE% "%USERPROFILE%\.marketplace-mcp\app\serve.py" ozon --selfcheck
echo.
pause
endlocal
exit /b 0

REM --- helpers ---------------------------------------------------------------

:detect
REM Sets PYEXE to a working Python 3.10+ command, or leaves it undefined.
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if defined PYEXE call :checkpy
if defined PYEXE goto :eof
where python >nul 2>nul && set "PYEXE=python"
if defined PYEXE call :checkpy
goto :eof

:checkpy
REM Clears PYEXE unless it launches a real Python >= 3.10 (the Microsoft
REM Store stub exits non-zero here, as does Python 2/3.9).
%PYEXE% -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul
if errorlevel 1 set "PYEXE="
goto :eof
