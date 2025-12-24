<#
start_elasticsearch.ps1

Improved script to create/start an Elasticsearch container named 'es-ik',
wait for the HTTP endpoint to become available, and print cluster info.

Behavior:
- If a container named 'es-ik' exists and is stopped, it will be started.
- If no such container exists, a new container will be created from the
  local image 'local/elasticsearch-ik:8.10.2'.
- The script waits for the Elasticsearch HTTP API (http://localhost:9200)
  to return a 200 status code, retrying with a configurable timeout.
#>

Write-Host "Starting Elasticsearch container (es-ik)..." -ForegroundColor Green

# helper: run docker and return trimmed output
function Run-DockerCommand($cmd) {
    $output = & docker $cmd 2>&1
    return $output
}

# Check for existing container (by name)
$existing = docker ps -a --filter "name=es-ik" --format "{{.Names}}|{{.Status}}|{{.Image}}" | Select-String -Pattern "^es-ik" -Quiet

if ($existing) {
    Write-Host "Container 'es-ik' exists. Ensuring it is running..." -ForegroundColor Yellow
    $statusLine = docker ps -a --filter "name=es-ik" --format "{{.Names}}|{{.Status}}|{{.Image}}"
    if ($statusLine -match "Up") {
        Write-Host "Container 'es-ik' is already running." -ForegroundColor Cyan
    } else {
        Write-Host "Starting existing container 'es-ik'..." -ForegroundColor Yellow
        docker start es-ik | Out-Null
    }
} else {
    Write-Host "Creating and starting new container 'es-ik'..." -ForegroundColor Yellow

    # Create data directory if missing
    $dataDir = "C:\esdata\elasticsearch-ik\data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
        Write-Host "Created data directory: $dataDir" -ForegroundColor Cyan
    }

    # Run container
    $runCmd = @(
        'run', '-d',
        '--name', 'es-ik',
        '-p', '9200:9200',
        '-p', '9300:9300',
        '-e', 'discovery.type=single-node',
        '-e', 'ES_JAVA_OPTS=-Xms2g -Xmx2g',
        '-e', 'xpack.security.enabled=false',
        '-v', "${dataDir}:/usr/share/elasticsearch/data",
        'local/elasticsearch-ik:8.10.2'
    ) -join ' '

    $out = Run-DockerCommand $runCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to run docker container: $out" -ForegroundColor Red
        exit 1
    }
    Write-Host "Container started (detached)." -ForegroundColor Cyan
}

Write-Host "Waiting for Elasticsearch HTTP API at http://localhost:9200 ..." -ForegroundColor Yellow

# Wait for ES to become available using Invoke-RestMethod to avoid HTML parsing prompts
$maxRetries = 60
$retry = 0
$esReady = $false
$info = $null

while (-not $esReady -and $retry -lt $maxRetries) {
    try {
        # Use Invoke-RestMethod which returns parsed JSON (no HTML parsing prompts)
        $info = Invoke-RestMethod -Uri "http://localhost:9200" -ErrorAction Stop
        if ($info -and $info.version) {
            $esReady = $true
            break
        }
    } catch {
        # ignore and retry
    }
    $retry++
    Write-Host "Waiting... ($retry/$maxRetries)" -ForegroundColor Gray
    Start-Sleep -Seconds 2
}

if ($esReady) {
    Write-Host "Elasticsearch is ready at http://localhost:9200" -ForegroundColor Green
    try {
        Write-Host ("Cluster: {0}  Version: {1}" -f $info.cluster_name, $info.version.number) -ForegroundColor Cyan
    } catch {
        Write-Host "Warning: failed to format cluster info." -ForegroundColor Yellow
    }
} else {
    Write-Host "Elasticsearch did not become ready within timeout." -ForegroundColor Red
    Write-Host "Check container logs: docker logs es-ik" -ForegroundColor Yellow
    exit 1
}
