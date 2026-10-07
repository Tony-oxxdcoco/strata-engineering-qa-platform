@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 20+ first. See GETTING_STARTED.md.
  pause
  exit /b 1
)
node scripts\setup.mjs
if errorlevel 1 pause
