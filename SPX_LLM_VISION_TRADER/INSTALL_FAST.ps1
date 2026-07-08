$ErrorActionPreference = "Stop"
$repo = "https://github.com/la1ani/SPX_ACCEPTANCE_PLATFORM.git"
$root = "C:\SPX_ACCEPTANCE_PLATFORM"
$project = "$root\SPX_LLM_VISION_TRADER"

Write-Host "SPX fast installer" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "Git missing. Install Git first, then rerun." -ForegroundColor Red
  exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python missing. Install Python 3.12 first, then rerun." -ForegroundColor Red
  exit 1
}

if (Test-Path $root) {
  cd $root
  git pull
} else {
  cd C:\
  git clone $repo
}

cd $project
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium

if (-not (Test-Path ".env")) { copy .env.example .env }

$envText = Get-Content ".env" -Raw
$lines = @(
  "GOOGLE_SHEET_ID=1kdjheVgAkeJWrL7qJjUZZhY4Ms2HI_mC_kovWMXFkXE",
  "CALL_SHEET_TAB=CALLS",
  "PUT_SHEET_TAB=PUTS",
  "CALL_LINK_TAB=CALLS_LINK",
  "PUT_LINK_TAB=PUTS_LINK",
  "SCREENSHOT_INTERVAL_SECONDS=15",
  "BATTLE_LOOP_SECONDS=10",
  "ALERT_MODE=terminal",
  "STRICT_MODE_ENABLED=true",
  "STRICT_MODE_BLOCK=false"
)
foreach ($line in $lines) {
  $name = $line.Split("=")[0]
  if ($envText -notmatch "(?m)^$name=") { Add-Content ".env" $line }
}

Write-Host "Open .env and fill the private values, then save." -ForegroundColor Yellow
notepad .env
Read-Host "Press ENTER after saving .env"

if (-not (Test-Path "service_account.json")) {
  Write-Host "Copy service_account.json into this folder, then press ENTER:" -ForegroundColor Yellow
  Write-Host $project
  Read-Host
}

.\.venv\Scripts\python.exe main.py --test-strict
.\.venv\Scripts\python.exe main.py --test-db
.\.venv\Scripts\python.exe main.py --test-alert
.\.venv\Scripts\python.exe main.py --test-sheets

Write-Host "Install done. Run live with:" -ForegroundColor Green
Write-Host "cd $project"
Write-Host ".\.venv\Scripts\python.exe main.py"
