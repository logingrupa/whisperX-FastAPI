<#
Restarts the "\WhisperX Backend" scheduled task. Requires Administrator: the
task runs as SYSTEM, so a non-elevated shell cannot end or start it.

Refuses to stop the server while a job is in flight (a restart mid-job loses
the transcription and leaks the user's concurrency slot, which has rate=0 and
never refills on its own).

Verification after boot: waits for /docs, then reads GET /api/usage with the
key in the caller's WSP_API_KEY (or the fleet .env) and prints the limit fields.
#>
param(
    [string]$TaskName = '\WhisperX Backend',
    [int]$BootTimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole('Administrators')
if (-not $isAdmin) { throw "Not elevated. Run this from an Administrator PowerShell." }

# --- gate: no job may be in flight -----------------------------------------
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$counter = Join-Path $PSScriptRoot 'inflight_count.py'
$inFlight = & $python $counter (Join-Path $repoRoot 'records.db')
if ($LASTEXITCODE -ne 0) { throw "In-flight check failed: $inFlight" }
if ([int]$inFlight -ne 0) { throw "$inFlight job(s) in flight. Wait for the queue to drain." }
Write-Host "Queue idle."

# --- restart ----------------------------------------------------------------
schtasks /End /TN $TaskName | Out-Null
Write-Host "Stop requested. Waiting for the server to exit..."
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Process python -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
}
if (Get-Process python -ErrorAction SilentlyContinue) {
    Write-Warning "python.exe still running. An orphan interactive instance holding logs\backend-boot.log makes every task run fail with no log output. Close that console before continuing."
}

schtasks /Run /TN $TaskName | Out-Null
Write-Host "Start requested. Waiting for /docs..."
$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
$up = $false
while (-not $up -and (Get-Date) -lt $deadline) {
    try {
        $up = (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/docs' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200
    } catch { Start-Sleep -Seconds 5 }
}
if (-not $up) { throw "Backend did not answer within $BootTimeoutSeconds s. Check logs\backend-boot.log." }
Write-Host "Backend up."

# --- verify /api/usage ------------------------------------------------------
$key = $env:WSP_API_KEY
if (-not $key) {
    $envFile = Join-Path $env:USERPROFILE '.claude\skills\.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^WSP_API_KEY=(.+)$' | Select-Object -First 1
        if ($line) { $key = $line.Matches[0].Groups[1].Value.Trim() }
    }
}
if (-not $key) { Write-Warning "No WSP_API_KEY found. Skipping the /api/usage check."; return }

# Cloudflare answers 403 "error code: 1010" to unrecognised clients, so send a
# browser User-Agent. A bare tool UA fails at the edge, never reaching uvicorn.
$headers = @{
    Authorization = "Bearer $key"
    'User-Agent'  = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
}
$usage = Invoke-RestMethod -Uri 'https://wsp.kingdom.lv/api/usage' -Headers $headers
$usage | Select-Object plan_tier, unlimited, hour_count, hour_limit, daily_minutes_used, daily_minutes_limit | Format-List
if ($usage.unlimited -ne $true) { Write-Warning "unlimited is not true. Is the key flagged, and did the new usage code load?" }
if ($null -ne $usage.hour_limit) { Write-Warning "hour_limit is not null. The /api/usage change did not load." }
