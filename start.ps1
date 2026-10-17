# One-click start for Windows: starts Docker Desktop if needed, waits for the engine, starts SnapFix, opens the browser.
# Usage: double-click start.cmd  (or: powershell -ExecutionPolicy Bypass -File start.ps1 [-Reset])
param([switch]$Reset)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Test-DockerReady {
    docker ps *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-DockerReady)) {
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dd)) {
        Write-Host "Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
        exit 1
    }
    Write-Host "Starting Docker Desktop..." -ForegroundColor Cyan
    Start-Process $dd
    $deadline = (Get-Date).AddMinutes(4)
    while (-not (Test-DockerReady)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host "Docker Desktop did not become ready in 4 minutes. Open it manually, wait for 'Engine running', then run this again." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Seconds 3
    }
}
Write-Host "Docker engine is ready." -ForegroundColor Green

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (add ANTHROPIC_API_KEY there for live AI; without it SnapFix runs in offline demo mode)." -ForegroundColor Yellow
}

Write-Host "Starting SnapFix (first run builds images: ~5 minutes)..." -ForegroundColor Cyan
docker compose up -d --build --wait
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose failed. See: docker compose logs backend" -ForegroundColor Red
    exit 1
}

if ($Reset) {
    Write-Host "Resetting demo data..." -ForegroundColor Cyan
    docker compose exec -T backend python -m app.demo_reset | Out-Null
}

Write-Host ""
Write-Host "SnapFix is running:" -ForegroundColor Green
Write-Host "  Report (phone view)  http://localhost:3000/r/engr-101"
Write-Host "  Dispatcher queue     http://localhost:3000/tickets"
Write-Host "  Manager dashboard    http://localhost:3000/dashboard"
Write-Host "  Evaluation           http://localhost:3000/eval"
Write-Host "  Operator console     http://localhost:3000/admin   (token in .env: ADMIN_TOKEN)"
Write-Host ""
Write-Host "Stop with stop.cmd. Restore the demo starting state with: start.cmd -Reset"
Start-Process "http://localhost:3000/dashboard"
