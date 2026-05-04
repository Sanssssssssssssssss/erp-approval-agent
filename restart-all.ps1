param(
    [switch]$NoBrowser,
    [switch]$RefreshDeps,
    [switch]$ClearFrontendCache,
    [int[]]$StopPorts = @(3000, 3007, 8015, 2024)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $Root "src\frontend"
$FrontendCache = Join-Path $FrontendDir ".next"
$StartLocalScript = Join-Path $Root "start-local.ps1"

function Stop-ListenersOnPort {
    param(
        [int]$Port
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "[stop] Port $Port is already free." -ForegroundColor DarkGray
        return
    }

    $processIds = $connections |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -ne $PID }

    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        $name = if ($process) { $process.ProcessName } else { "unknown" }
        Write-Host "[stop] Stopping PID $processId ($name) on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Wait-PortsFree {
    param(
        [int[]]$Ports,
        [int]$TimeoutSeconds = 12
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $busy = foreach ($port in $Ports) {
            Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        }
        if (-not $busy) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Clear-FrontendCacheIfRequested {
    if (-not $ClearFrontendCache) {
        return
    }
    if (-not (Test-Path $FrontendCache)) {
        Write-Host "[cache] Frontend .next cache does not exist." -ForegroundColor DarkGray
        return
    }

    $resolvedCache = Resolve-Path $FrontendCache
    $resolvedFrontend = Resolve-Path $FrontendDir
    if (-not $resolvedCache.Path.StartsWith($resolvedFrontend.Path)) {
        throw "Refusing to remove cache outside src/frontend: $($resolvedCache.Path)"
    }

    Remove-Item -LiteralPath $resolvedCache.Path -Recurse -Force
    Write-Host "[cache] Removed src/frontend/.next." -ForegroundColor Yellow
}

if (-not (Test-Path $StartLocalScript)) {
    throw "Missing start-local.ps1 at $StartLocalScript"
}

Set-Location $Root

Write-Host ""
Write-Host "Restarting ERP Approval Agent Workbench..." -ForegroundColor Cyan
Write-Host "- This is a real restart: existing listeners are stopped first." -ForegroundColor Cyan
Write-Host "- Backend target:  http://127.0.0.1:8015" -ForegroundColor Cyan
Write-Host "- Frontend target: http://127.0.0.1:3000" -ForegroundColor Cyan
Write-Host ""

foreach ($port in $StopPorts | Select-Object -Unique) {
    Stop-ListenersOnPort -Port $port
}

if (-not (Wait-PortsFree -Ports $StopPorts)) {
    Write-Host "[warn] Some ports are still busy. Startup script will report any hard conflicts." -ForegroundColor Yellow
}

Clear-FrontendCacheIfRequested

$arguments = @("-ExecutionPolicy", "Bypass", "-File", $StartLocalScript, "-Restart")
if ($NoBrowser) {
    $arguments += "-NoBrowser"
}
if ($RefreshDeps) {
    $arguments += "-RefreshDeps"
}

Write-Host "[start] Launching backend and frontend..." -ForegroundColor Cyan
& powershell @arguments

Write-Host ""
Write-Host "Restart command finished." -ForegroundColor Green
Write-Host "- Frontend: http://127.0.0.1:3000"
Write-Host "- Backend:  http://127.0.0.1:8015"
Write-Host "- Health:   http://127.0.0.1:8015/health"
