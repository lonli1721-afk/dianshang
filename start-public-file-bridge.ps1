param(
  [int]$LocalApiPort = 6181,
  [int]$RemoteBridgePort = 16181,
  [string]$SshUser = "liling",
  [string]$SshHost = "106.53.49.23",
  [string]$KeyPath = "C:\Users\Administrator\.ssh\id_ed25519"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting public file bridge..."
Write-Host "  Public URL prefix: http://$SshHost/local-test/public-files/"
Write-Host "  Remote tunnel: 127.0.0.1:$RemoteBridgePort -> 127.0.0.1:$LocalApiPort"
Write-Host ""

$sshArgs = @(
  "-i", $KeyPath,
  "-o", "IdentitiesOnly=yes",
  "-o", "ExitOnForwardFailure=yes",
  "-N",
  "-R", "127.0.0.1:$RemoteBridgePort`:127.0.0.1:$LocalApiPort",
  "$SshUser@$SshHost"
)

Start-Process -WindowStyle Hidden -FilePath "C:\Windows\System32\OpenSSH\ssh.exe" -ArgumentList $sshArgs
Start-Sleep -Seconds 2

Write-Host "Bridge started. Keep your local API server running on 127.0.0.1:$LocalApiPort."
