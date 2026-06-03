param(
  [int]$ApiPort = 6181
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Join-Path $Root "server"
$DataDir = Join-Path $Root ".local-data"
$Python = Join-Path $ServerDir ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:USER_DATA_DIR = $DataDir
$env:PUBLIC_BASE_URL = "http://106.53.49.23/local-test"

Set-Location $ServerDir
& $Python main.py --host 127.0.0.1 --port $ApiPort
