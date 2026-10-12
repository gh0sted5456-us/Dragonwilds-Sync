@echo off
setlocal
cd /d "%~dp0app-next"
if errorlevel 1 exit /b 1
call npm ci
if errorlevel 1 exit /b %errorlevel%
call npm run build:next
if errorlevel 1 exit /b %errorlevel%
call npm run prepare:standalone
if errorlevel 1 exit /b %errorlevel%
call npx electron-builder --win portable --x64 --publish never
exit /b %errorlevel%
