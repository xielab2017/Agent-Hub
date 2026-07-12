# Hermes-ALI launcher for Windows (PowerShell)
# Usage:  .\start.ps1
#         .\start.ps1 -Port 9000 -Password "secret"

param(
  [string]$HostAddress = $env:HERMES_ALI_HOST,
  [int]$Port = 0,
  [string]$Password = $env:HERMES_ALI_PASSWORD,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $HostAddress) { $HostAddress = "0.0.0.0" }
if ($Port -le 0) {
  if ($env:HERMES_ALI_PORT) { $Port = [int]$env:HERMES_ALI_PORT } else { $Port = 8765 }
}

$env:HERMES_ALI_HOST = $HostAddress
$env:HERMES_ALI_PORT = "$Port"
if ($Password) { $env:HERMES_ALI_PASSWORD = $Password }

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
  Write-Error "Python 3.9+ is required. Install from https://www.python.org/downloads/"
}

$argsList = @("bootstrap.py", "--host", $HostAddress, "--port", "$Port")
if ($NoBrowser) { $argsList += "--no-browser" }
if ($Password) { $argsList += @("--password", $Password) }

& $py.Source @argsList
