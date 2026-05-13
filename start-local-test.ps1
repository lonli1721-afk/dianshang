param(
  [int]$ApiPort = 6181,
  [int]$WebPort = 6180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Join-Path $Root "server"
$WebDir = Join-Path $Root "react-ui"
$DataDir = Join-Path $Root ".local-data"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

if (-not (Test-Path (Join-Path $ServerDir ".venv\Scripts\python.exe"))) {
  Write-Host "Creating Python virtual environment..."
  py -3 -m venv (Join-Path $ServerDir ".venv")
}

$Python = Join-Path $ServerDir ".venv\Scripts\python.exe"
Write-Host "Installing backend dependencies..."
& $Python -m pip install -r (Join-Path $ServerDir "requirements.txt")

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  Push-Location $WebDir
  npm install
  Pop-Location
}

$backendCommand = @"
`$env:USER_DATA_DIR='$DataDir'
cd '$ServerDir'
& '$Python' main.py --host 127.0.0.1 --port $ApiPort
"@

$frontendCommand = @"
`$env:VITE_API_URL='http://127.0.0.1:$ApiPort'
cd '$WebDir'
npm run dev -- --host 127.0.0.1 --port $WebPort
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand

$Url = "http://127.0.0.1:$WebPort"
Write-Host ""
Write-Host "Local test server is starting:"
Write-Host "  Web: $Url"
Write-Host "  API: http://127.0.0.1:$ApiPort"
Write-Host "  Data: $DataDir"
Write-Host ""
Write-Host "This local version uses .local-data and will not affect the online server."
Start-Process $Url
