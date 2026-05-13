param(
  [int]$ApiPort = 6181,
  [int]$WebPort = 6180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Join-Path $Root "server"
$WebDir = Join-Path $Root "react-ui"
$DataDir = Join-Path $Root ".local-data"
$VenvDir = Join-Path $ServerDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Test-PythonCommand {
  param([string]$CommandName)

  try {
    if ($CommandName -eq "py") {
      & py -3 --version *> $null
    } else {
      & $CommandName --version *> $null
    }
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

function Find-RealPython {
  foreach ($Candidate in @("py", "python", "python3")) {
    $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if (-not $Command) { continue }

    $Source = [string]$Command.Source
    if ($Source -like "*\Microsoft\WindowsApps\python*.exe") { continue }

    if (Test-PythonCommand $Candidate) {
      return $Candidate
    }
  }

  $LocalPythonRoot = Join-Path $env:LocalAppData "Programs\Python"
  if (Test-Path $LocalPythonRoot) {
    $PythonExe = Get-ChildItem $LocalPythonRoot -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notlike "*\Lib\venv\*" } |
      Sort-Object FullName -Descending |
      Select-Object -First 1

    if ($PythonExe) {
      return $PythonExe.FullName
    }
  }

  return $null
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
Set-Content -Path (Join-Path $WebDir ".env.local") -Value "VITE_PROXY_TARGET=http://127.0.0.1:$ApiPort" -Encoding UTF8

if ((Test-Path $VenvDir) -and -not (Test-Path $VenvPython)) {
  Write-Host "Removing incomplete Python virtual environment..."
  Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating Python virtual environment..."
  $PythonLauncher = Find-RealPython
  if (-not $PythonLauncher) {
    throw "Python 3 was not found. Please install Python 3.12 and run this script again."
  }

  if ($PythonLauncher -eq "py") {
    & py -3 -m venv $VenvDir
  } else {
    & $PythonLauncher -m venv $VenvDir
  }

  if (-not (Test-Path $VenvPython)) {
    throw "Failed to create Python virtual environment."
  }
}

$Python = $VenvPython
Write-Host "Installing backend dependencies..."
& $Python -m pip install -r (Join-Path $ServerDir "requirements.txt")

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  Push-Location $WebDir
  try {
    npm install
  } finally {
    Pop-Location
  }
}

$backendCommand = @"
`$env:USER_DATA_DIR='$DataDir'
cd '$ServerDir'
& '$Python' main.py --host 127.0.0.1 --port $ApiPort
"@

$frontendCommand = @"
Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
`$env:VITE_PROXY_TARGET='http://127.0.0.1:$ApiPort'
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
