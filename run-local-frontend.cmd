@echo off
set "ROOT=%~dp0"
set "WEB_DIR=%ROOT%react-ui"
set "VITE_PROXY_TARGET=http://127.0.0.1:6181"
set "VITE_API_URL="
cd /d "%WEB_DIR%"
> ".env.local" echo VITE_PROXY_TARGET=http://127.0.0.1:6181
npm.cmd run dev -- --host 127.0.0.1 --port 6180
