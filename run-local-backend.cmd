@echo off
set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "WEB_DIST_DIR=%ROOT%react-ui\dist"
set "DATA_DIR=%USERPROFILE%\.game-video-tool"
set "USER_DATA_DIR=%DATA_DIR%"
set "UI_DIST_DIR=%WEB_DIST_DIR%"
set "PUBLIC_BASE_URL=http://106.53.49.23/local-test"
set "ALLOW_LOCAL_FILE_FALLBACK=true"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
cd /d "%SERVER_DIR%"
"%SERVER_DIR%\.venv\Scripts\python.exe" main.py --host 127.0.0.1 --port 6182
