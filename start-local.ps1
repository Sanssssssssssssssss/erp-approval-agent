param(
    [switch]$All,
    [switch]$Validate,
    [switch]$Benchmark,
    [switch]$NoStart,
    [switch]$Restart,
    [switch]$NoBrowser,
    [switch]$RefreshDeps,
    [int]$BenchmarkLimit = 3,
    [string]$BenchmarkOutput = "artifacts\benchmarks\latest\rfp_security_smoke.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "src\frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BackendEnv = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
$FrontendNodeModules = Join-Path $FrontendDir "node_modules"
$ValidateScript = Join-Path $BackendDir "scripts\dev\validate-phase14-mvp.ps1"
$StartDevScript = Join-Path $BackendDir "scripts\dev\start-dev.ps1"

if ($All) {
    $Validate = $true
    $Benchmark = $true
}

function Get-NpmCommand {
    foreach ($commandName in @("npm.cmd", "npm")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "npm was not found. Install Node.js LTS or restart VS Code so PATH is refreshed."
}

function Ensure-BackendEnvFile {
    if (Test-Path $BackendEnv) {
        Write-Host "[env] backend/.env already exists. Keeping local values." -ForegroundColor Green
        return
    }
    if (-not (Test-Path $BackendEnvExample)) {
        throw "Missing backend/.env.example."
    }
    Copy-Item -Path $BackendEnvExample -Destination $BackendEnv
    Write-Host "[env] Created backend/.env from backend/.env.example. Add real model keys locally when needed." -ForegroundColor Yellow
}

function Ensure-BackendVenv {
    $created = $false
    if (-not (Test-Path $BackendPython)) {
        Write-Host "[setup] Creating backend virtual environment..." -ForegroundColor Cyan
        Push-Location $BackendDir
        try {
            py -3.13 -m venv .venv
            $created = $true
        } finally {
            Pop-Location
        }
    }

    if ($created -or $RefreshDeps) {
        Write-Host "[setup] Installing backend dependencies..." -ForegroundColor Cyan
        & $BackendPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
        return
    }

    Write-Host "[setup] Backend virtual environment ready." -ForegroundColor Green
}

function Ensure-FrontendDeps {
    if ((Test-Path $FrontendNodeModules) -and -not $RefreshDeps) {
        Write-Host "[setup] Frontend dependencies ready." -ForegroundColor Green
        return
    }
    Write-Host "[setup] Installing frontend dependencies..." -ForegroundColor Cyan
    $npm = Get-NpmCommand
    Push-Location $FrontendDir
    try {
        & $npm install
    } finally {
        Pop-Location
    }
}

function Run-FinalValidation {
    Write-Host "[validate] Running Phase 14 MVP validation..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File $ValidateScript
}

function Run-LegacyBenchmarkSmoke {
    Write-Host "[benchmark] Running legacy RFP/security compatibility smoke benchmark..." -ForegroundColor Cyan
    Write-Host "[benchmark] This is not an ERP approval benchmark." -ForegroundColor Yellow
    & $BackendPython (Join-Path $BackendDir "benchmarks\run_harness_benchmark.py") `
        --suite rfp_security `
        --limit $BenchmarkLimit `
        --output $BenchmarkOutput
}

function Start-Workbench {
    Write-Host "[start] Starting ERP Approval Agent Workbench..." -ForegroundColor Cyan
    $arguments = @("-ExecutionPolicy", "Bypass", "-File", $StartDevScript, "-InstallIfMissing")
    if ($Restart) {
        $arguments += "-Restart"
    }
    if ($NoBrowser) {
        $arguments += "-NoBrowser"
    }
    & powershell @arguments
}

Ensure-BackendEnvFile
Ensure-BackendVenv
Ensure-FrontendDeps

if ($Validate) {
    Run-FinalValidation
}

if ($Benchmark) {
    Run-LegacyBenchmarkSmoke
}

if (-not $NoStart) {
    Start-Workbench
} else {
    Write-Host "[done] Setup completed. Startup skipped because -NoStart was provided." -ForegroundColor Green
}

Write-Host ""
Write-Host "Useful URLs after startup:" -ForegroundColor Green
Write-Host "- Frontend: http://127.0.0.1:3000"
Write-Host "- Backend:  http://127.0.0.1:8015"
Write-Host "- Health:   http://127.0.0.1:8015/health"
