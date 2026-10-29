# Windows x64 desktop ALPHA (unsigned). Run from repository root.
param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not $SkipInstall) {
  python -m pip install -r backend/requirements-desktop.txt pyinstaller pillow
  if ($LASTEXITCODE -ne 0) { throw "Desktop Python dependencies failed" }
}
python scripts/make_desktop_icons.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }
python -m PyInstaller --clean --noconfirm --onefile --name astratube-backend --paths backend --collect-submodules app --collect-submodules uvicorn --distpath backend/dist --workpath backend/build --specpath backend/build backend/desktop_server.py
if ($LASTEXITCODE -ne 0) { throw "FastAPI PyInstaller build failed" }

python scripts/smoke_desktop.py backend/dist/astratube-backend.exe
if ($LASTEXITCODE -ne 0) { throw "FastAPI sidecar smoke test failed" }

$target = (rustc --print host-tuple).Trim()
if ($target -ne "x86_64-pc-windows-msvc") { throw "Only Windows x64 MSVC builds are supported in this alpha: $target" }
$binaryDir = Join-Path $root "desktop/src-tauri/binaries"
New-Item -ItemType Directory -Force $binaryDir | Out-Null
Copy-Item backend/dist/astratube-backend.exe (Join-Path $binaryDir "astratube-backend-$target.exe") -Force

Push-Location frontend
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "Frontend npm ci failed" }
  $env:VITE_DESKTOP_BUILD = "1"
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "Desktop frontend build failed" }
} finally {
  Remove-Item Env:VITE_DESKTOP_BUILD -ErrorAction SilentlyContinue
  Pop-Location
}

Push-Location desktop
try {
  npx --yes "@tauri-apps/cli@2" build --bundles nsis
  if ($LASTEXITCODE -ne 0) { throw "Tauri desktop installer build failed" }
} finally { Pop-Location }

Write-Host "Unsigned alpha installers: desktop/src-tauri/target/release/bundle/nsis/"
