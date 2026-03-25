#Requires -Version 5.1
# XBVR Stack Manager
# Run from PowerShell: .\windows\xbvr-manager.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

# Paths
$PROJECT_ROOT      = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ENV_FILE          = Join-Path $PSScriptRoot ".env"
$DOCKER_DIR        = Join-Path $PROJECT_ROOT "docker"
$COMPOSE_FILE      = Join-Path $DOCKER_DIR "docker-compose.yml"
$MARIADB_DATA_DIR  = Join-Path $PROJECT_ROOT "data\mariadb"
$XBVR_DATA_DIR     = Join-Path $PROJECT_ROOT "data\xbvr"

$DIRS = @(
    $MARIADB_DATA_DIR,
    $XBVR_DATA_DIR
)

# Using default plugin paths: /var/lib/docker-plugins/rclone/config and /var/lib/docker-plugins/rclone/cache

function Write-Header {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host "              XBVR Stack Manager                 " -ForegroundColor Cyan
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host " Project root: $PROJECT_ROOT" -ForegroundColor DarkGray
    Write-Host ""
}

function Read-EnvValue {
    param([string]$Key)
    if (-not (Test-Path $ENV_FILE)) { return $null }
    $line = Get-Content $ENV_FILE | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
    return $null
}

function Confirm-DockerRunning {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker is not running. Please start it first." -ForegroundColor Red
        return $false
    }
    return $true
}

function Pause-ForUser {
    Write-Host ""
    Write-Host "Press any key to return to the menu..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Initialize-Directories {
    Write-Host "Creating required directories under $PROJECT_ROOT ..." -ForegroundColor Yellow
    foreach ($dir in $DIRS) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Host "  Created: $dir" -ForegroundColor Green
        }
        else {
            Write-Host "  Already exists: $dir" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "OK: Directories ready." -ForegroundColor Green
    Pause-ForUser
}

function Install-RclonePlugin {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }

    Write-Host "Checking if rclone plugin is already installed..." -ForegroundColor Yellow
    $existing = docker plugin ls --format "{{.Name}}" 2>&1 | Where-Object { $_ -like "*rclone*" }
    if ($existing) {
        Write-Host "  Plugin already installed: $existing" -ForegroundColor DarkGray
        Pause-ForUser
        return
    }

    Write-Host "Installing itstoggle/docker-volume-rclone_rd plugin..." -ForegroundColor Yellow
    Write-Host "  Using Docker's default plugin paths." -ForegroundColor DarkGray
    Write-Host ""

    try {
        docker plugin install itstoggle/docker-volume-rclone_rd:amd64 `
            args="-v" `
            --alias rclone `
            --grant-all-permissions

        Write-Host ""
        Write-Host "OK: Plugin installed successfully." -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR: Plugin installation failed: $_" -ForegroundColor Red
    }
    Pause-ForUser
}

function Verify-RclonePlugin {
    param(
        [switch]$SilentIfExists
    )

    $plugin = docker plugin ls --format "{{.Name}}" 2>&1 | Where-Object { $_ -like "*rclone*" }
    if (-not $plugin) {
        Write-Host "ERROR: rclone plugin not found. Please install it first (option 2)." -ForegroundColor Red
        return $false
    }

    if (-not $SilentIfExists) {
        Write-Host "  rclone plugin is installed." -ForegroundColor Green
    }
    return $true
}

function Start-Stack {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }
    if (-not (Test-Path $COMPOSE_FILE)) {
        Write-Host "ERROR: docker-compose.yml not found at $COMPOSE_FILE" -ForegroundColor Red
        Pause-ForUser
        return
    }

    if (-not (Verify-RclonePlugin -SilentIfExists)) {
        Write-Host "  Please install the rclone plugin first (option 2)." -ForegroundColor Yellow
        Pause-ForUser
        return
    }

    Write-Host ""
    Write-Host "Starting XBVR stack (MariaDB + XBVR)..." -ForegroundColor Yellow
    Write-Host "  Real-Debrid volume will be created by docker compose..." -ForegroundColor DarkGray
    Push-Location $DOCKER_DIR
    try {
        docker compose --env-file $ENV_FILE up -d
        Write-Host ""
        Write-Host "OK: Stack started." -ForegroundColor Green
        $port = Read-EnvValue "XBVR_PORT"
        if (-not $port) { $port = "9999" }
        Write-Host "  XBVR web UI --> http://localhost:$port" -ForegroundColor Cyan
    }
    catch {
        Write-Host "ERROR: Failed to start stack: $_" -ForegroundColor Red
    }
    finally {
        Pop-Location
    }
    Pause-ForUser
}

function Stop-Stack {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }
    Write-Host "Stopping XBVR stack..." -ForegroundColor Yellow
    Push-Location $DOCKER_DIR
    try {
        docker compose --env-file $ENV_FILE down -v
        Write-Host ""
        Write-Host "OK: Stack stopped and volumes removed." -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR: Failed to stop stack: $_" -ForegroundColor Red
    }
    finally {
        Pop-Location
    }
    Pause-ForUser
}

function Show-Logs {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }
    Write-Host "Showing live logs (Ctrl+C to stop)..." -ForegroundColor Yellow
    Push-Location $DOCKER_DIR
    try {
        docker compose --env-file $ENV_FILE logs -f
    }
    catch {
        # Ctrl+C raises an exception - ignore it
    }
    finally {
        Pop-Location
    }
    Pause-ForUser
}

function Invoke-PartialCleanup {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }

    Write-Host "================================================" -ForegroundColor Yellow
    Write-Host "   PARTIAL CLEANUP - Rclone plugin only          " -ForegroundColor Yellow
    Write-Host "================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This will:"
    Write-Host "  - Stop and remove all stack containers and volumes"
    Write-Host "  - Uninstall the rclone Docker plugin"
    Write-Host ""
    Write-Host "This will NOT touch:"  -ForegroundColor Green
    Write-Host "  - $MARIADB_DATA_DIR  (your database)" -ForegroundColor Green
    Write-Host "  - $XBVR_DATA_DIR  (your XBVR config)" -ForegroundColor Green
    Write-Host ""
    $confirm = Read-Host "Type YES to proceed"
    if ($confirm -ne "YES") {
        Write-Host "Cancelled." -ForegroundColor DarkGray
        Pause-ForUser
        return
    }

    Push-Location $DOCKER_DIR

    Write-Host ""
    Write-Host "Stopping containers and removing volumes..." -ForegroundColor Yellow
    docker compose --env-file $ENV_FILE down -v 2>&1 | Out-Null

    Write-Host "Disabling and removing rclone plugin..." -ForegroundColor Yellow
    docker plugin disable rclone 2>&1 | Out-Null
    docker plugin rm rclone 2>&1 | Out-Null

    Write-Host ""
    Write-Host "OK: Partial cleanup complete." -ForegroundColor Green
    Write-Host "  Your database and XBVR config are untouched." -ForegroundColor Green
    Write-Host "  To reconnect Real-Debrid, run options 2 then 3 again." -ForegroundColor Cyan

    Pop-Location
    Pause-ForUser
}

function Invoke-Cleanup {
    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }

    Write-Host "=================================================" -ForegroundColor Red
    Write-Host "   WARNING: FULL CLEANUP - THIS IS DESTRUCTIVE   " -ForegroundColor Red
    Write-Host "=================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "This will:" -ForegroundColor Red
    Write-Host "  - Stop and remove all stack containers and volumes" -ForegroundColor Red
    Write-Host "  - Uninstall the rclone Docker plugin" -ForegroundColor Red
    Write-Host "  - Delete $MARIADB_DATA_DIR  (all database files)" -ForegroundColor Red
    Write-Host "  - Delete $XBVR_DATA_DIR  (all XBVR config and metadata)" -ForegroundColor Red
    Write-Host ""
    Write-Host "  This cannot be undone."
    Write-Host ""
    $confirm = Read-Host "Type YES to proceed"
    if ($confirm -ne "YES") {
        Write-Host "Cancelled." -ForegroundColor DarkGray
        Pause-ForUser
        return
    }

    Push-Location $DOCKER_DIR

    Write-Host ""
    Write-Host "Stopping containers and removing volumes..." -ForegroundColor Yellow
    docker compose --env-file $ENV_FILE down -v 2>&1 | Out-Null

    Write-Host "Disabling and removing rclone plugin..." -ForegroundColor Yellow
    docker plugin disable rclone 2>&1 | Out-Null
    docker plugin rm rclone 2>&1 | Out-Null

    Write-Host "Deleting $MARIADB_DATA_DIR ..." -ForegroundColor Yellow
    if (Test-Path $MARIADB_DATA_DIR) {
        Remove-Item -Recurse -Force $MARIADB_DATA_DIR
        Write-Host "  Deleted." -ForegroundColor Green
    } else {
        Write-Host "  Already gone." -ForegroundColor DarkGray
    }

    Write-Host "Deleting $XBVR_DATA_DIR ..." -ForegroundColor Yellow
    if (Test-Path $XBVR_DATA_DIR) {
        Remove-Item -Recurse -Force $XBVR_DATA_DIR
        Write-Host "  Deleted." -ForegroundColor Green
    } else {
        Write-Host "  Already gone." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "OK: Full cleanup complete." -ForegroundColor Green
    Write-Host "  To reinstall from scratch, run option 0 (Full setup)." -ForegroundColor Cyan

    Pop-Location
    Pause-ForUser
}

function Invoke-FullSetup {
    Write-Host 'Starting full setup (steps 1 through 3)...' -ForegroundColor Cyan
    Write-Host ''

    Write-Host '[Step 1/3] Creating directories...' -ForegroundColor Yellow
    foreach ($dir in $DIRS) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Host "  Created: $dir" -ForegroundColor Green
        }
        else {
            Write-Host "  Already exists: $dir" -ForegroundColor DarkGray
        }
    }
    Write-Host 'OK: Directories ready.' -ForegroundColor Green
    Write-Host ''

    if (-not (Confirm-DockerRunning)) { Pause-ForUser; return }

    Write-Host '[Step 2/3] Installing rclone_RD plugin...' -ForegroundColor Yellow
    $existing = docker plugin ls --format '{{.Name}}' 2>&1 | Where-Object { $_ -like '*rclone*' }
    if ($existing) {
        Write-Host "  Plugin already installed: $existing" -ForegroundColor DarkGray
    }
    else {
        try {
            docker plugin install itstoggle/docker-volume-rclone_rd:amd64 `
                args="-v" `
                --alias rclone `
                --grant-all-permissions
            Write-Host 'OK: Plugin installed.' -ForegroundColor Green
        }
        catch {
            Write-Host "ERROR: Plugin installation failed: $_" -ForegroundColor Red
            Pause-ForUser
            return
        }
    }
    Write-Host ''

    Write-Host '[Step 3/3] Starting stack (volumes will be created by docker compose)...' -ForegroundColor Yellow
    if (-not (Test-Path $COMPOSE_FILE)) {
        Write-Host "ERROR: docker-compose.yml not found at $COMPOSE_FILE" -ForegroundColor Red
        Pause-ForUser
        return
    }
    Push-Location $DOCKER_DIR
    try {
        docker compose --env-file $ENV_FILE up -d
        Write-Host ''
        Write-Host 'OK: Stack started.' -ForegroundColor Green
        $port = Read-EnvValue 'XBVR_PORT'
        if (-not $port) { $port = '9999' }
        Write-Host "  XBVR web UI --> http://localhost:$port" -ForegroundColor Cyan
    }
    catch {
        Write-Host "ERROR: Failed to start stack: $_" -ForegroundColor Red
    }
    finally {
        Pop-Location
    }

    Pause-ForUser
}



# Main Menu Loop
while ($true) {
    Write-Header

    Write-Host "  SETUP" -ForegroundColor DarkCyan
    Write-Host "  [0] Full setup  (runs steps 1 through 3 automatically)"
    Write-Host "  [1] Create required directories"
    Write-Host "  [2] Install rclone_RD Docker plugin"
    Write-Host ""
    Write-Host "  DAILY USE" -ForegroundColor DarkCyan
    Write-Host "  [3] Start stack  (volumes managed by docker compose)"
    Write-Host "  [4] Stop stack + remove volumes"
    Write-Host "  [8] View live logs"
    Write-Host ""
    Write-Host "  MAINTENANCE" -ForegroundColor DarkCyan
    Write-Host "  [6] Partial cleanup (remove plugin only)"
    Write-Host "  [7] Full cleanup (remove everything including app data)"
    Write-Host ""
    Write-Host "  [Q] Quit"
    Write-Host ""

    $choice = Read-Host "Choose an option"

    switch ($choice.ToUpper()) {
        "0" { Invoke-FullSetup }
        "1" { Initialize-Directories }
        "2" { Install-RclonePlugin }
        "3" { Start-Stack }
        "4" { Stop-Stack }
        "6" { Invoke-PartialCleanup }
        "7" { Invoke-Cleanup }
        "8" { Show-Logs }
        "Q" { Write-Host "Bye!" -ForegroundColor Cyan; exit 0 }
        default {
            Write-Host "Invalid option. Please try again." -ForegroundColor Red
            Start-Sleep 1
        }
    }
}
