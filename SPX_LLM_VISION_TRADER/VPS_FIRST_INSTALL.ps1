# SPX LLM Vision Trader - Windows VPS first install script
# Run this in Administrator PowerShell on the Windows VPS.

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/la1ani/SPX_ACCEPTANCE_PLATFORM.git"
$InstallRoot = "C:\SPX_ACCEPTANCE_PLATFORM"
$ProjectDir = Join-Path $InstallRoot "SPX_LLM_VISION_TRADER"
$LogDir = "C:\SPX_INSTALL_LOGS"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("install_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-Step($message) {
    $line = "[`$(Get-Date -Format 'HH:mm:ss')] $message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

function Test-CommandExists($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-ChocolateyIfMissing {
    if (Test-CommandExists choco) {
        Write-Step "Chocolatey already installed."
        return
    }
    Write-Step "Installing Chocolatey package manager..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Install-Packages {
    Install-ChocolateyIfMissing
    Write-Step "Installing Google Chrome, Git, and Python 3.12..."
    choco install -y googlechrome git python312 | Tee-Object -FilePath $LogFile -Append
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Clone-Or-UpdateRepo {
    if (Test-Path $InstallRoot) {
        Write-Step "Repository folder already exists. Pulling latest code..."
        Push-Location $InstallRoot
        git pull | Tee-Object -FilePath $LogFile -Append
        Pop-Location
    } else {
        Write-Step "Cloning repository to $InstallRoot..."
        git clone $RepoUrl $InstallRoot | Tee-Object -FilePath $LogFile -Append
    }
}

function Setup-Project {
    if (-not (Test-Path $ProjectDir)) {
        throw "Project folder not found: $ProjectDir"
    }
    Push-Location $ProjectDir

    Write-Step "Creating Python virtual environment..."
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv | Tee-Object -FilePath $LogFile -Append
    }

    Write-Step "Installing Python requirements..."
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip | Tee-Object -FilePath $LogFile -Append
    & ".venv\Scripts\pip.exe" install -r requirements.txt | Tee-Object -FilePath $LogFile -Append

    if (-not (Test-Path ".env")) {
        Write-Step "Creating .env from .env.example..."
        Copy-Item ".env.example" ".env"
    }

    Write-Step "Project setup complete."
    Pop-Location
}

function Create-DesktopShortcut {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "SPX BOT VPS.lnk"
    $TargetPath = Join-Path $ProjectDir "RUN_WITH_CHROME_LOGIN.bat"
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetPath
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
    $Shortcut.Save()
    Write-Step "Desktop shortcut created: $ShortcutPath"
}

Write-Step "Starting SPX bot Windows VPS install..."
Install-Packages
Clone-Or-UpdateRepo
Setup-Project
Create-DesktopShortcut

Write-Host ""
Write-Host "============================================================"
Write-Host "INSTALL DONE"
Write-Host "============================================================"
Write-Host "Next steps:"
Write-Host "1. Copy your service_account.json into: $ProjectDir"
Write-Host "2. Open and fill: $ProjectDir\.env"
Write-Host "3. Run once manually: $ProjectDir\RUN_WITH_CHROME_LOGIN.bat"
Write-Host "4. Login to TradingView with Google in Chrome."
Write-Host "5. After it works once, create Task Scheduler daily run using RUN_AUTO_VPS.bat."
Write-Host ""
Write-Host "Install log saved here: $LogFile"
Write-Host "============================================================"
