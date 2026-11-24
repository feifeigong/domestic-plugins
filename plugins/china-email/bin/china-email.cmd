@echo off
setlocal
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"

py.exe -3 -c "import sys; sys.exit(sys.version_info<(3,10))" >nul 2>&1
if not errorlevel 1 (
    py.exe -3 -u "%~dp0..\src\china_email_mcp.py"
    exit /b
)

for %%N in (python.exe python3.exe) do (
    for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" %%N 2^>nul') do (
        if /i not "%%~dpP"=="%LOCALAPPDATA%\Microsoft\WindowsApps\" (
            "%%P" -c "import sys; sys.exit(sys.version_info<(3,10))" >nul 2>&1
            if not errorlevel 1 (
                "%%P" -u "%~dp0..\src\china_email_mcp.py"
                exit /b
            )
        )
    )
)

>&2 echo [china-email] Python 3.10+ is required. Install Python and restart ChatGPT.
exit /b 1
