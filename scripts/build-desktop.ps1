# Windows x64 portable ALPHA (unsigned, no installer). Run from repository root.
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
python -m PyInstaller --clean --noconfirm --onefile --name astratube-backend --paths (Join-Path $root "backend") --hidden-import app.main --collect-submodules app --collect-submodules uvicorn --distpath backend/dist --workpath backend/build --specpath backend/build backend/desktop_server.py
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
  # 只編譯執行檔，不產生安裝程式；tauri-build 會把 sidecar 複製到 target/release
  npx --yes "@tauri-apps/cli@2" build --no-bundle
  if ($LASTEXITCODE -ne 0) { throw "Tauri desktop build failed" }
} finally { Pop-Location }

# 組出免安裝版資料夾：主程式與背景服務必須在同一層（sidecar 從主程式所在資料夾尋找）
$release = Join-Path $root "desktop/src-tauri/target/release"
$outDir = Join-Path $root "desktop/portable"
$portable = Join-Path $outDir "AstraTube-Portable"
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Force $portable | Out-Null
Copy-Item (Join-Path $release "astratube-desktop.exe") (Join-Path $portable "AstraTube.exe")
Copy-Item (Join-Path $release "astratube-backend.exe") (Join-Path $portable "astratube-backend.exe")
# 使用說明等文件（腳本內不寫中文檔名，避免 Windows PowerShell 5.1 以 ANSI 讀取時亂碼）
Copy-Item (Join-Path $root "desktop/portable-template/*") $portable
Copy-Item (Join-Path $root "LICENSE") (Join-Path $portable "LICENSE.txt")
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $portable
Compress-Archive -Path $portable -DestinationPath (Join-Path $outDir "AstraTube-Portable-x64.zip") -Force

Write-Host "Unsigned portable alpha: desktop/portable/AstraTube-Portable/ (zip: desktop/portable/AstraTube-Portable-x64.zip)"
