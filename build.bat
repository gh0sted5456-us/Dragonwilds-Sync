@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PAUSE_ON_EXIT=1"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

set "BUILD_LOG=%CD%\build.log"
set "LAUNCH_ERR=%CD%\build-launch-error.tmp"
set "BUILD_RC=1"
if exist "%LAUNCH_ERR%" del /q "%LAUNCH_ERR%" >nul 2>nul
>"%BUILD_LOG%" echo [Dragonwilds Sync Build Launcher]
>>"%BUILD_LOG%" echo Project: %CD%
>>"%BUILD_LOG%" echo Started: %DATE% %TIME%
>>"%BUILD_LOG%" echo.

title Dragonwilds Sync 2.7.31 - Portable Build

echo ============================================================
echo   Dragonwilds Sync 2.7.31 - Portable Windows Build
echo ============================================================
echo Project:   %CD%
echo Build log: "%BUILD_LOG%"
echo.

if not exist "%CD%\scripts\build_windows.ps1" (
    echo [ERROR] Missing scripts\build_windows.ps1
    >>"%BUILD_LOG%" echo [ERROR] Missing scripts\build_windows.ps1
    goto :finish
)
if not exist "%CD%\backend\dragonwilds_service.py" (
    echo [ERROR] Missing backend\dragonwilds_service.py
    >>"%BUILD_LOG%" echo [ERROR] Missing backend\dragonwilds_service.py
    goto :finish
)
if not exist "%CD%\backend\DragonwildsSync.Service.spec" (
    echo [ERROR] Missing backend\DragonwildsSync.Service.spec
    >>"%BUILD_LOG%" echo [ERROR] Missing backend\DragonwildsSync.Service.spec
    goto :finish
)

where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Windows PowerShell was not found.
    >>"%BUILD_LOG%" echo [ERROR] Windows PowerShell was not found.
    goto :finish
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\build_windows.ps1" -ProjectRoot "%CD%" -LogPath "%BUILD_LOG%" 2>"%LAUNCH_ERR%"
set "BUILD_RC=%ERRORLEVEL%"

if exist "%LAUNCH_ERR%" (
    for %%A in ("%LAUNCH_ERR%") do if %%~zA GTR 0 (
        echo.
        echo [PowerShell launcher diagnostics]
        type "%LAUNCH_ERR%"
        >>"%BUILD_LOG%" echo.
        >>"%BUILD_LOG%" echo [PowerShell launcher diagnostics]
        type "%LAUNCH_ERR%" >>"%BUILD_LOG%"
    )
    del /q "%LAUNCH_ERR%" >nul 2>nul
)

:finish
>>"%BUILD_LOG%" echo.
>>"%BUILD_LOG%" echo Launcher exit code: %BUILD_RC%
>>"%BUILD_LOG%" echo Launcher finished: %DATE% %TIME%

if not "%BUILD_RC%"=="0" (
    echo.
    echo ============================================================
    echo   BUILD FAILED ^(exit code %BUILD_RC%^)
    echo ============================================================
    echo Full log: "%BUILD_LOG%"
    echo.
    echo The window will remain open so the error can be read or copied.
    goto :done
)

echo.
echo ============================================================
echo   PORTABLE BUILD COMPLETE
echo ============================================================
echo Output: "%CD%\release\Dragonwilds Sync and Launcher-Portable-2.7.31.exe"
echo Log:    "%BUILD_LOG%"
echo.
echo Opening the release folder now.
start "" explorer "%CD%\release" >nul 2>&1

:done
if "%PAUSE_ON_EXIT%"=="1" (
    echo.
    pause
)
exit /b %BUILD_RC%
