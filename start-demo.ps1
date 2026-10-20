# Starts the app and a fresh cloudflared quick tunnel, then points everything at the tunnel's new address.
# Run after every PC restart:  powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = ".\.venv\Scripts\python.exe"

# 1. Stop an old app or tunnel started from this folder, and keep their logs.
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "uvicorn leadagent\.app|cloudflared.*localhost:8000" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
foreach ($f in "app.log", "app.out.log", "tunnel.log", "tunnel.out.log") {
    if (Test-Path "logs\$f") { Move-Item "logs\$f" "logs\old-$stamp-$f" -Force }
}

# 2. Start the tunnel and read its new address.
Start-Process cloudflared -ArgumentList "tunnel", "--protocol", "http2", "--url", "http://localhost:8000" `
    -RedirectStandardOutput logs\tunnel.out.log -RedirectStandardError logs\tunnel.log -WindowStyle Hidden
$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
    Start-Sleep 2
    $hit = Select-String -Path logs\tunnel.log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($hit) { $url = $hit.Matches.Value }
}
if (-not $url) { throw "The tunnel gave no address in 60 s. See logs\tunnel.log." }
Write-Host "Tunnel address: $url"

# 3. Put it in .env (edited by Python so the file keeps its encoding; no other line is touched).
& $python -c "import pathlib,re,sys; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^PUBLIC_BASE_URL=.*$', 'PUBLIC_BASE_URL='+sys.argv[1], p.read_text(encoding='utf-8')), encoding='utf-8')" $url

# 4. Start the app.
Start-Process $python -ArgumentList "-m", "uvicorn", "leadagent.app:app", "--port", "8000" `
    -RedirectStandardOutput logs\app.out.log -RedirectStandardError logs\app.log -WindowStyle Hidden

# 5. Wait until the address works from outside (a new address can take a minute to become live).
$live = $false
for ($i = 0; $i -lt 24 -and -not $live; $i++) {
    Start-Sleep 5
    try { $live = (Invoke-WebRequest "$url/health" -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200 } catch {}
}
if (-not $live) {
    throw "$url is not reachable after 2 minutes. If logs\tunnel.log shows 'i/o timeout', this network blocks the tunnel: switch to the mobile hotspot and run this again."
}

# 6. Point every active institute's Telegram bot at the new address.
foreach ($line in & $python -m leadagent.cli list) {  # lines look like "8  brightpath  owner chat: ..."
    $slug = ($line -split "\s+")[1]
    Write-Host "${slug}: " -NoNewline
    & $python -m leadagent.cli set-webhook --slug $slug
}

Write-Host ""
Write-Host "Ready. Dashboard: $url/dash"
