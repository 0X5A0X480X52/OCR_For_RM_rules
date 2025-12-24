"""Bootstrap script: install dependencies and run the pipeline"""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PDF OCR -> Elasticsearch pipeline" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "1. Checking Python environment..." -ForegroundColor Green
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ $pythonVersion" -ForegroundColor White
} else {
    Write-Host "   ✗ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# 2. Check Docker
Write-Host ""
Write-Host "2. Checking Docker..." -ForegroundColor Green
$dockerVersion = docker --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ $dockerVersion" -ForegroundColor White
} else {
    Write-Host "   ✗ Docker not found. Please install Docker Desktop" -ForegroundColor Red
    exit 1
}

# 3. Build ES Docker image
Write-Host ""
Write-Host "3. Building Elasticsearch Docker image..." -ForegroundColor Green
Push-Location docker\elasticsearch-ik
$buildResult = .\build.ps1
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Docker image build failed" -ForegroundColor Red
    exit 1
}

# 4. Start ES container
Write-Host ""
Write-Host "4. Starting Elasticsearch container..." -ForegroundColor Green
.\start_elasticsearch.ps1

if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Elasticsearch failed to start" -ForegroundColor Red
    exit 1
}

# 5. Install Python dependencies
Write-Host ""
Write-Host "5. Installing Python dependencies..." -ForegroundColor Green
Write-Host "   (this may take a few minutes)" -ForegroundColor Yellow
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Failed to install Python dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "   ✓ Dependencies installed" -ForegroundColor White

# 6. Run main program
Write-Host ""
Write-Host "6. Running the processing pipeline..." -ForegroundColor Green
Write-Host ""

python main.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Processing completed!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Results are saved in the output/ directory" -ForegroundColor Yellow
Write-Host "Elasticsearch endpoint: http://localhost:9200" -ForegroundColor Yellow
Write-Host ""
