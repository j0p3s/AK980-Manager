@echo off
rem AK980 Manager launcher: installs Python if it is missing, then starts the program.
rem The program installs its own packages (Pillow, numpy, soundcard) and keeps itself up to date - see bootstrap.py.
setlocal
cd /d "%~dp0"

call :find
if defined PYW goto :run

echo Python was not found. Installing Python 3.12 for the current user (one time, needs internet)...
where winget >nul 2>nul
if errorlevel 1 (
    echo winget is not available. Please install Python 3.12 or newer from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then start this file again.
    pause
    exit /b 1
)
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
rem a fresh install is not on PATH of this window yet, so look in the default per-user folder as well
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\pythonw.exe" set "PYW=%%D\pythonw.exe"
if not defined PYW call :find
if not defined PYW (
    echo Python was installed, but could not be started from here. Close this window and start this file again.
    pause
    exit /b 1
)

:run
start "" "%PYW%" "%~dp0AK980 Manager.pyw"
exit /b 0

:find
set "PYW="
for %%C in (pyw.exe pythonw.exe) do (
    if not defined PYW (
        for /f "delims=" %%P in ('where %%C 2^>nul') do (
            if not defined PYW (
                "%%P" -c "import tkinter" >nul 2>nul && set "PYW=%%P"
            )
        )
    )
)
exit /b 0
