# Build the Elasticsearch image with IK plugin
# Usage: Open PowerShell, cd to this folder and run: .\build.ps1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir

# Tag must match what test base expects by default
docker build -t local/elasticsearch-ik:8.10.2 .

Pop-Location
