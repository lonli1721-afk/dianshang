@echo off
set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "DATA_DIR=%ROOT%.local-data"
set "USER_DATA_DIR=%DATA_DIR%"
set "PUBLIC_BASE_URL=http://106.53.49.23/local-test"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
cd /d "%SERVER_DIR%"
"%SERVER_DIR%\.venv\Scripts\python.exe" main.py --host 127.0.0.1 --port 6181
