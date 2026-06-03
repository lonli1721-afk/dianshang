param(
  [int]$ApiPort = 6181,
  [int]$WebPort = 6180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$WebDir = Join-Path $Root "react-ui"

Set-Content -Path (Join-Path $WebDir ".env.local") -Value "VITE_PROXY_TARGET=http://127.0.0.1:$ApiPort" -Encoding UTF8
Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
$env:VITE_PROXY_TARGET = "http://127.0.0.1:$ApiPort"

Set-Location $WebDir
npm.cmd run dev -- --host 127.0.0.1 --port $WebPort
