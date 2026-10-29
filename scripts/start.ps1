# Youtube Card Reader - start script (Windows PowerShell).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$BackendPort  = if ($env:YCR_BACKEND_PORT)  { $env:YCR_BACKEND_PORT }  else { 8420 }
$FrontendPort = if ($env:YCR_FRONTEND_PORT) { $env:YCR_FRONTEND_PORT } else { 15273 }

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Error "$cmd not found. $hint"; exit 1 }
}
Need python "Install Python 3.10+ from https://www.python.org/downloads/"
Need npm    "Install Node.js from https://nodejs.org/"

# First run: backend environment
if (-not (Test-Path "backend\.venv\Scripts\python.exe")) {
  Write-Host "-> First run: creating the Python environment (3-8 minutes)..."
  Push-Location backend
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install --upgrade pip -q
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt -q
  Pop-Location
}

# First run: frontend packages
if (-not (Test-Path "frontend\node_modules")) {
  Write-Host "-> First run: installing frontend packages (1-2 minutes)..."
  Push-Location frontend; npm install --silent; Pop-Location
}

function PortUp($port) {
  $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (PortUp $BackendPort)) {
  Write-Host "-> Starting backend on :$BackendPort..."
  Start-Process -FilePath ".\backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$BackendPort" `
    -WorkingDirectory "backend" -WindowStyle Hidden
}
if (-not (PortUp $FrontendPort)) {
  Write-Host "-> Starting frontend on :$FrontendPort..."
  $env:PORT = $FrontendPort
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c","npm run dev" `
    -WorkingDirectory "frontend" -WindowStyle Hidden
}

for ($i = 0; $i -lt 60; $i++) { if (PortUp $FrontendPort) { break }; Start-Sleep -Milliseconds 500 }
Start-Process "http://127.0.0.1:$FrontendPort"
Write-Host "Youtube Card Reader is running at http://127.0.0.1:$FrontendPort"
