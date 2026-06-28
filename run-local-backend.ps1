param(
  [int]$ApiPort = 6182,
  [switch]$BuildUi
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Join-Path $Root "server"
$WebDir = Join-Path $Root "react-ui"
$WebDistDir = Join-Path $WebDir "dist"
$WorkspaceRoot = Split-Path -Parent $Root
$BundledNodeDir = Join-Path $WorkspaceRoot "work\node-v22.12.0-win-x64"
$BundledNode = Join-Path $BundledNodeDir "node.exe"
$BundledNpm = Join-Path $BundledNodeDir "node_modules\npm\bin\npm-cli.js"
$DataDir = Join-Path $env:USERPROFILE ".game-video-tool"
$Python = Join-Path $ServerDir ".venv\Scripts\python.exe"

function Stop-LocalPort {
  param([int]$Port)

  $Connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
  if (-not $Connections.Count) { return }

  $ProcessIds = $Connections |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -ne $PID }

  foreach ($ProcessId in $ProcessIds) {
    Write-Host "Stopping existing process on port $Port (PID $ProcessId)..."
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }

  Start-Sleep -Seconds 1
}

function Invoke-UiBuild {
  $Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue

  Push-Location $WebDir
  try {
    if ($Npm) {
      & $Npm.Source run build
      return
    }

    if ((Test-Path $BundledNode) -and (Test-Path $BundledNpm)) {
      $env:PATH = "$BundledNodeDir;$env:PATH"
      & $BundledNode $BundledNpm run build
      return
    }

    throw "npm.cmd was not found, and bundled Node was not found at $BundledNode. Install Node.js or run without -BuildUi if react-ui\dist already exists."
  } finally {
    Pop-Location
  }
}

if (-not (Test-Path $Python)) {
  throw "Python virtual environment was not found: $Python"
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:USER_DATA_DIR = $DataDir
$env:UI_DIST_DIR = $WebDistDir
$env:PUBLIC_BASE_URL = "http://106.53.49.23/local-test"
$env:ALLOW_LOCAL_FILE_FALLBACK = "true"

if ($BuildUi) {
  Write-Host "Building frontend..."
  Invoke-UiBuild
}

if (-not (Test-Path (Join-Path $WebDistDir "index.html"))) {
  throw "react-ui\dist is missing. Run: .\run-local-backend.ps1 -BuildUi"
}

Stop-LocalPort -Port $ApiPort

Write-Host ""
Write-Host "Starting local app:"
Write-Host "  URL:  http://127.0.0.1:$ApiPort"
Write-Host "  Data: $DataDir"
Write-Host "  UI:   $WebDistDir"
Write-Host ""
Write-Host "Keep this PowerShell window open. Press Ctrl+C to stop."
Write-Host ""

Set-Location $ServerDir
& $Python main.py --host 127.0.0.1 --port $ApiPort
