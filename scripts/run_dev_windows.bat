@echo off
setlocal
cd /d "%~dp0\.."

if not exist "node_modules\electron\package.json" goto install_deps
if not exist "node_modules\monaco-editor\package.json" goto install_deps
goto start_app

:install_deps
echo Installing/updating Electron and launcher UI dependencies...
call pnpm install
if errorlevel 1 (
  echo.
  echo Development dependency install failed.
  pause
  exit /b 1
)

:start_app
call pnpm start
if errorlevel 1 (
  echo.
  echo Dragonwilds Sync exited with an error.
  pause
  exit /b 1
)
