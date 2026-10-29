# 免安裝版冒煙測試（Windows）。驗證真正的 GUI 主程式＋背景服務，而不只是後端：
#   1. 放在含中文與空白的路徑也能啟動，背景服務開始監聽
#   2. 資料只寫在程式旁的 data 資料夾，不寫入 %APPDATA%／%LOCALAPPDATA%
#   3. 正常關閉（WM_CLOSE）與強制結束後，背景服務都會在時限內結束
#   4. 資料夾無法寫入時不啟動背景服務，視窗仍可開啟（顯示原因）
param([Parameter(Mandatory = $true)][string]$PortableDir)
$ErrorActionPreference = "Stop"

$tempRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$testRoot = Join-Path $tempRoot ("可攜 測試 " + [guid]::NewGuid().ToString("N").Substring(0, 6))
$appDir = Join-Path $testRoot "AstraTube-Portable"
New-Item -ItemType Directory -Force $testRoot | Out-Null
Copy-Item -Recurse (Resolve-Path $PortableDir) $appDir
$exe = Join-Path $appDir "AstraTube.exe"
$roaming = Join-Path $env:APPDATA "dev.jingfeng.astratube"
$local = Join-Path $env:LOCALAPPDATA "dev.jingfeng.astratube"
$hadRoaming = Test-Path $roaming
$hadLocal = Test-Path $local

function Backends { @(Get-Process -Name "astratube-backend" -ErrorAction SilentlyContinue) }

function Wait-Until([scriptblock]$Condition, [int]$Seconds, [string]$What) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 500
  }
  throw "Timed out after ${Seconds}s: $What"
}

function Assert-BackendListening {
  Wait-Until { (Backends).Count -gt 0 } 60 "backend process started"
  Wait-Until {
    foreach ($p in Backends) {
      if (Get-NetTCPConnection -OwningProcess $p.Id -State Listen -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
  } 90 "backend listening on a loopback port"
  foreach ($p in Backends) {
    foreach ($c in @(Get-NetTCPConnection -OwningProcess $p.Id -State Listen -ErrorAction SilentlyContinue)) {
      if ($c.LocalAddress -ne "127.0.0.1") { throw "Backend must only listen on 127.0.0.1, got $($c.LocalAddress)" }
    }
  }
}

try {
  # 前面步驟（後端冒煙測試）留下的行程會讓判斷失準，先確認環境乾淨
  Wait-Until { (Backends).Count -eq 0 } 30 "no backend left from earlier steps"

  # 1. 啟動
  $app = Start-Process -FilePath $exe -WorkingDirectory $appDir -PassThru
  Assert-BackendListening
  Wait-Until { Test-Path (Join-Path $appDir "data\webview\EBWebView") } 60 "WebView2 data inside the portable folder"
  if (-not (Test-Path (Join-Path $appDir "data\app"))) { throw "data\app was not created next to the executable" }
  Write-Host "Started from: $appDir"

  # 2. 不寫入使用者設定資料夾
  if (-not $hadRoaming -and (Test-Path $roaming)) { throw "Portable build wrote to $roaming" }
  if (-not $hadLocal -and (Test-Path $local)) { throw "Portable build wrote to $local" }

  # 3a. 正常關閉：送出 WM_CLOSE（不加 /F），等同使用者按視窗的 X
  & taskkill.exe /PID $app.Id | Out-Null
  Wait-Until { $app.HasExited } 30 "AstraTube exits after WM_CLOSE"
  Wait-Until { (Backends).Count -eq 0 } 30 "backend stops after a normal close"
  Write-Host "Normal close: no backend left"

  # 3b. 強制結束（模擬當掉）：背景服務靠父行程監看自行結束
  $app = Start-Process -FilePath $exe -WorkingDirectory $appDir -PassThru
  Assert-BackendListening
  Stop-Process -Id $app.Id -Force
  Wait-Until { (Backends).Count -eq 0 } 30 "backend stops after AstraTube is killed"
  Write-Host "Forced exit: no backend left"
  if (-not (Test-Path (Join-Path $appDir "data\app"))) { throw "data folder disappeared" }

  # 4. 無法寫入的位置：拒絕在資料夾內建立子資料夾與檔案
  $lockedDir = Join-Path $testRoot "Locked"
  Copy-Item -Recurse (Resolve-Path $PortableDir) $lockedDir
  & icacls.exe $lockedDir /deny "$($env:USERNAME):(AD,WD)" | Out-Null
  $locked = Start-Process -FilePath (Join-Path $lockedDir "AstraTube.exe") -WorkingDirectory $lockedDir -PassThru
  Start-Sleep -Seconds 12
  if ($locked.HasExited) { throw "AstraTube should stay open to show the unwritable-folder message" }
  if ((Backends).Count -ne 0) { throw "Backend must not start when the portable folder is not writable" }
  if (Test-Path (Join-Path $lockedDir "data")) { throw "Unexpected data folder in a locked location" }
  Stop-Process -Id $locked.Id -Force
  Write-Host "Unwritable folder: window opened, backend not started"

  Write-Host "Portable smoke test passed"
}
finally {
  Get-Process -Name "AstraTube", "astratube-backend" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  if (Test-Path (Join-Path $testRoot "Locked")) { & icacls.exe (Join-Path $testRoot "Locked") /remove:d "$($env:USERNAME)" | Out-Null }
}
