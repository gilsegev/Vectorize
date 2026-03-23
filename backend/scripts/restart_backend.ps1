param(
  [int]$Port = 8000,
  [int]$TimeoutSec = 45
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$pythonExe = Join-Path $backendDir ".venv\\Scripts\\python.exe"
$logDir = Join-Path $backendDir "logs"
$outLog = Join-Path $logDir "backend.out.log"
$errLog = Join-Path $logDir "backend.err.log"

if (!(Test-Path $pythonExe)) {
  throw "Backend venv python not found: $pythonExe"
}

if (!(Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir | Out-Null
}

function Stop-BackendProcessById([int]$ProcessId) {
  try {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    Write-Host "Stopped backend process PID=$ProcessId"
  } catch {
    Write-Host "Backend PID=$ProcessId already stopped or inaccessible"
  }
}

# Stop known backend server processes for this repo only.
$escapedPythonExe = [regex]::Escape($pythonExe)
$backendProcesses = Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -match $escapedPythonExe -and
    $_.CommandLine -match "uvicorn app.main:app"
  }

foreach ($proc in $backendProcesses) {
  Stop-BackendProcessById -ProcessId $proc.ProcessId
}

# If something is still listening on requested port, stop only if it is backend uvicorn.
$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
  $listenerIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($id in $listenerIds) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -match "uvicorn app.main:app") {
      Stop-BackendProcessById -ProcessId $id
    } elseif ($proc) {
      throw "Port $Port is in use by PID=$id ($($proc.Name)). Refusing to kill non-backend process."
    } else {
      throw "Port $Port appears in use by PID=$id, but process metadata is unavailable."
    }
  }
}

if (Test-Path $outLog) { Remove-Item $outLog -Force }
if (Test-Path $errLog) { Remove-Item $errLog -Force }

$args = @("-m", "uvicorn", "app.main:app", "--port", "$Port")
$proc = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory $backendDir -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Write-Host "Started backend PID=$($proc.Id) on port $Port"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$healthy = $false
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 500
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
      $healthy = $true
      break
    }
  } catch {
    # keep waiting
  }
}

if (-not $healthy) {
  Write-Host "Backend did not become healthy within $TimeoutSec seconds."
  if (Test-Path $errLog) {
    Write-Host "--- backend.err.log (tail) ---"
    Get-Content $errLog -Tail 80
  }
  if (Test-Path $outLog) {
    Write-Host "--- backend.out.log (tail) ---"
    Get-Content $outLog -Tail 80
  }
  exit 1
}

Write-Host "Backend healthy at http://127.0.0.1:$Port/health"
