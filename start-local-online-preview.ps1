param(
  [int]$Port = 6180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Join-Path $Root "server"
$WebDistDir = Join-Path $Root "react-ui\dist"
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

if (-not (Test-Path (Join-Path $WebDistDir "index.html"))) {
  throw "react-ui\dist is missing. Please sync the online build before starting local preview."
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

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
}

$Python = $VenvPython
Write-Host "Installing backend dependencies..."
& $Python -m pip install -r (Join-Path $ServerDir "requirements.txt")

$serverCommand = @"
`$env:USER_DATA_DIR='$DataDir'
`$env:UI_DIST_DIR='$WebDistDir'
`$env:PUBLIC_BASE_URL='http://106.53.49.23/local-test'
cd '$ServerDir'
& '$Python' main.py --host 127.0.0.1 --port $Port
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $serverCommand

$Url = "http://127.0.0.1:$Port"
Write-Host ""
Write-Host "Local online-preview server is starting:"
Write-Host "  URL:  $Url"
Write-Host "  Data: $DataDir"
Write-Host "  UI:   $WebDistDir"
Write-Host ""
Write-Host "This preview uses local data only and will not affect the online server."
Write-Host "If you need Seedance/Wanxiang to read local uploaded files, run:"
Write-Host "  .\start-public-file-bridge.ps1 -LocalApiPort $Port"
Start-Process $Url
