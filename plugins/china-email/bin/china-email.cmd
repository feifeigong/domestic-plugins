@echo off
setlocal

set "platform=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "platform=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "platform=arm64"
set "runtime=%~dp0..\runtime\windows\%platform%\python.exe"
if not exist "%runtime%" (
    >&2 echo [china-email] Bundled Windows runtime is missing. Update and reinstall the plugin from its GitHub marketplace.
    exit /b 1
)

if /i "%~1"=="setup" (
    "%runtime%" -u "%~dp0..\src\china_email_mcp.py" setup
    exit /b
)

"%runtime%" -u "%~dp0..\src\china_email_mcp.py"
exit /b
