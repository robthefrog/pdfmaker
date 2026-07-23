@echo off
rem ============================================================
rem  Combine PDFs - double-click to merge every PDF in a folder
rem  into a single PDF file (kept in order).
rem  Tip: you can also drag a folder onto this file's icon.
rem
rem  The first time you run it, it quietly sets itself up
rem  (needs an internet connection just that once). After
rem  that it works offline. It shares the same private setup
rem  as the "Make PDF" launcher next to it.
rem
rem  All the real work happens in launcher.py, shared with the
rem  macOS launcher (Combine PDFs.command).
rem ============================================================
setlocal
cd /d "%~dp0"

rem Find Python 3: the python.org installer provides the "py" launcher;
rem plain "python" is checked as a fallback (the Microsoft Store stub fails
rem the version check, so it is never picked up by mistake).
set "PYCMD="
py -3 -c "" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD python -c "" >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto :run

echo Python 3 isn't installed yet - you only need to do this once.
echo.
echo   1. Go to:  https://www.python.org/downloads/windows/
echo   2. Download the latest "Windows installer (64-bit)".
echo   3. IMPORTANT: on the first screen tick "Add python.exe to PATH",
echo      then click "Install Now".
echo   4. Double-click this launcher again.
echo.
pause
exit /b 1

:run
%PYCMD% launcher.py combine %*
