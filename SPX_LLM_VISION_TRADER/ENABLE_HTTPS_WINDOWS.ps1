param(
    [string]$PublicIp = "74.208.237.154"
)

$ErrorActionPreference = "Stop"

$ProjectDir = "C:\SPX_ACCEPTANCE_PLATFORM\SPX_LLM_VISION_TRADER"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$CaddyDir = Join-Path $ProjectDir "tools\caddy"
$CaddyExe = Join-Path $CaddyDir "caddy.exe"
$CaddyZip = Join-Path $CaddyDir "caddy.zip"
$Caddyfile = Join-Path $CaddyDir "Caddyfile"
$HostName = (($PublicIp -replace '\.', '-') + ".sslip.io")
$HttpsBaseUrl = "https://$HostName"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "SPX HTTPS SETUP" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Public IP : $PublicIp"
Write-Host "HTTPS host: $HostName"
Write-Host ""

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

# Ensure Windows Firewall allows HTTP and HTTPS.
foreach ($port in 80, 443) {
    $ruleName = "SPX HTTPS Port $port"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow | Out-Null
        Write-Host "[OK] Windows Firewall rule created for TCP $port" -ForegroundColor Green
    } else {
        Write-Host "[OK] Windows Firewall already allows TCP $port" -ForegroundColor Green
    }
}

# Ensure the API is running on local port 8000.
$api8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $api8000) {
    Write-Host "Starting SPX dashboard API on 127.0.0.1:8000..."
    Start-Process -FilePath $PythonExe `
        -ArgumentList "dashboard_api.py" `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden
    Start-Sleep -Seconds 5
    $api8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $api8000) {
        throw "SPX dashboard API did not start on port 8000."
    }
}
Write-Host "[OK] SPX API listening on port 8000" -ForegroundColor Green

# If port 80 is occupied by the same SPX API, stop only that process so Caddy can bind to 80.
$port80 = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($port80) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($port80.OwningProcess)" -ErrorAction SilentlyContinue
    $cmd = [string]$proc.CommandLine
    if ($cmd -match "dashboard_api" -or $cmd -match "uvicorn.*dashboard_api") {
        Write-Host "Stopping SPX API instance currently occupying port 80 (PID $($port80.OwningProcess))..."
        Stop-Process -Id $port80.OwningProcess -Force
        Start-Sleep -Seconds 2
    } else {
        throw "Port 80 is occupied by another process (PID $($port80.OwningProcess)). Command: $cmd"
    }
}

# Download Caddy if needed.
New-Item -ItemType Directory -Force -Path $CaddyDir | Out-Null
if (-not (Test-Path $CaddyExe)) {
    Write-Host "Downloading Caddy for Windows..."
    Invoke-WebRequest `
        -Uri "https://caddyserver.com/api/download?os=windows&arch=amd64" `
        -OutFile $CaddyZip
    Expand-Archive -Path $CaddyZip -DestinationPath $CaddyDir -Force
    Remove-Item $CaddyZip -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $CaddyExe)) {
        throw "Caddy download completed but caddy.exe was not found."
    }
}
Write-Host "[OK] Caddy is available" -ForegroundColor Green

# Configure Caddy to obtain a trusted certificate automatically and proxy to the API.
@"
$HostName {
    reverse_proxy 127.0.0.1:8000
}
"@ | Set-Content -Path $Caddyfile -Encoding UTF8

# Stop old Caddy instances started from this folder only.
Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -eq $CaddyExe } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 1

$stdout = Join-Path $CaddyDir "caddy.out.log"
$stderr = Join-Path $CaddyDir "caddy.err.log"

Write-Host "Starting HTTPS reverse proxy..."
Start-Process -FilePath $CaddyExe `
    -ArgumentList "run --config `"$Caddyfile`"" `
    -WorkingDirectory $CaddyDir `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden

Start-Sleep -Seconds 10

$caddyProcess = Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -eq $CaddyExe } |
    Select-Object -First 1
if (-not $caddyProcess) {
    Write-Host "Caddy failed to stay running. Last error output:" -ForegroundColor Red
    if (Test-Path $stderr) { Get-Content $stderr -Tail 80 }
    throw "HTTPS reverse proxy failed to start."
}

Write-Host "[OK] Caddy running with PID $($caddyProcess.ProcessId)" -ForegroundColor Green

Write-Host ""
Write-Host "Testing local API..."
$localHealth = Invoke-RestMethod "http://127.0.0.1:8000/api/health"
Write-Host "[OK] Local API status: $($localHealth.status)" -ForegroundColor Green

Write-Host ""
Write-Host "Testing public HTTPS endpoint..."
try {
    $publicHealth = Invoke-RestMethod "$HttpsBaseUrl/api/health" -TimeoutSec 30
    Write-Host "[OK] HTTPS API status: $($publicHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "HTTPS may still be provisioning the certificate. Try again in 30-60 seconds." -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "USE THIS IN BASE44" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "VITE_SPX_API_BASE_URL=$HttpsBaseUrl" -ForegroundColor Green
Write-Host ""
Write-Host "Health endpoint: $HttpsBaseUrl/api/health"
Write-Host "Dashboard:       $HttpsBaseUrl/api/dashboard/current"
Write-Host "MTF:             $HttpsBaseUrl/api/mtf/current"
Write-Host ""
Write-Host "Caddy logs:"
Write-Host "  $stdout"
Write-Host "  $stderr"
