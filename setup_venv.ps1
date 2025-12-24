# Create and install dependencies into a local .venv
param(
    [string]$VenvPath = ".venv",
    [string]$Python = "python"
)

Write-Host "Creating virtual environment at '$VenvPath'..." -ForegroundColor Cyan

# Create venv
& $Python -m venv $VenvPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to create virtual environment using $Python" -ForegroundColor Red
    exit 1
}

$activate = "$PSScriptRoot\$VenvPath\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Host "Activation script not found: $activate" -ForegroundColor Red
    exit 1
}

Write-Host "Activating virtual environment..." -ForegroundColor Cyan
# Activate in current shell
. $activate

Write-Host "Upgrading pip and installing dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependency installation failed. See errors above." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Virtual environment prepared." -ForegroundColor Green
Write-Host ('To activate manually in this PowerShell session run: .\' + $VenvPath + '\Scripts\Activate.ps1') -ForegroundColor Yellow
Write-Host 'To run processing inside venv: python main.py' -ForegroundColor Yellow
