<#
Restarts the "\WhisperX Backend" scheduled task and proves a NEW process
serves. Requires Administrator: the task runs as SYSTEM.

Refuses to stop the server while a job is in flight (a restart mid-job loses
the transcription). Refusals that happen before anything was stopped throw a
message starting with "Restart refused:".

schtasks /End alone is not enough: once the launcher's cmd.exe has exited, the
python tree is no longer part of the task instance and keeps serving the old
code, and a python that is still importing holds logs\backend-boot.log so the
next launch cannot start uvicorn. So every uvicorn python of this repo is
killed explicitly. The restart only counts once a listener that started after
this script did is up and logs\backend-boot.log has a fresh "Application
startup complete"; a preflight abort, or a launcher that exited with nothing
listening, fails fast with the log tails.

Verification after boot reads GET /api/usage with the key in WSP_API_KEY
(process or user environment). It is advisory: an edge blip only warns.
#>
param(
    [string]$TaskName = '\WhisperX Backend',
    [int]$Port = 8000,
    [int]$StopTimeoutSeconds = 60,
    [int]$BootTimeoutSeconds = 900,
    [int]$TaskStartGraceSeconds = 60
)

if ($PSVersionTable.PSVersion.Major -lt 7) {
    # Windows PowerShell 5.1 turns a native command's stderr into a terminating
    # error under ErrorActionPreference=Stop; rerun under PowerShell 7.
    $pwsh = (Get-Command pwsh -ErrorAction Stop).Source
    $forwarded = @(foreach ($entry in $PSBoundParameters.GetEnumerator()) { "-$($entry.Key)"; "$($entry.Value)" })
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath @forwarded
    exit $LASTEXITCODE
}

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$bootLog = Join-Path $repoRoot 'logs\backend-boot.log'
$preflightLog = Join-Path $repoRoot 'logs\preflight.log'

function Get-ListenerProcessId {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Get-PythonTreeRoot([int]$ProcessId) {
    # Walk up while the parent is python.exe: uvicorn.exe's launcher python
    # owns the worker python that holds the socket.
    $current = $ProcessId
    while ($true) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if (-not $process) { return $current }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
        if (-not $parent -or $parent.Name -ne 'python.exe') { return $current }
        $current = [int]$parent.ProcessId
    }
}

function Get-BackendPythonProcessIds {
    # Every python of this repo running uvicorn app.main:app, listening or not.
    $venvPath = Join-Path $repoRoot '.venv'
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app\.main:app' -and
            $_.CommandLine -like "*$venvPath*"
        } |
        ForEach-Object { [int]$_.ProcessId }
}

function Get-LogTimestamp([string]$Line, [string]$Pattern, [string]$Format) {
    if ($Line -cnotmatch $Pattern) { return $null }
    $stamp = $Matches[1] -replace '\s+', ' '
    return [datetime]::ParseExact($stamp, $Format, [Globalization.CultureInfo]::InvariantCulture)
}

function Find-LogLineSince([string]$Path, [string]$Needle, [datetime]$Since, [string]$Pattern, [string]$Format) {
    # Last line containing $Needle (case-sensitive) whose leading timestamp is not older than $Since.
    $lines = Get-Content -LiteralPath $Path -Tail 400 -ErrorAction SilentlyContinue
    foreach ($line in ($lines | Where-Object { $_.Contains($Needle) } | Select-Object -Last 5)) {
        $stamp = Get-LogTimestamp $line $Pattern $Format
        if ($stamp -and $stamp -ge $Since) { return $line }
    }
    return $null
}

function Find-BootLogLineSince([string]$Needle, [datetime]$Since) {
    Find-LogLineSince $bootLog $Needle $Since '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})' 'yyyy-MM-dd HH:mm:ss'
}

function Find-PreflightAbortSince([datetime]$Since) {
    # preflight.log lines look like "[06.10.2026 16:45:07,18] aborting: ..." (the
    # hour is space-padded below 10, hence the whitespace collapse in Get-LogTimestamp).
    Find-LogLineSince $preflightLog 'aborting' $Since '^\[\s*(\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}:\d{2})' 'dd.MM.yyyy H:mm:ss'
}

function Get-LogTails {
    $boot = (Get-Content -LiteralPath $bootLog -Tail 15 -ErrorAction SilentlyContinue) -join "`n"
    $preflight = (Get-Content -LiteralPath $preflightLog -Tail 6 -ErrorAction SilentlyContinue) -join "`n"
    return "--- backend-boot.log (tail)`n$boot`n--- preflight.log (tail)`n$preflight"
}

function Wait-Until([scriptblock]$Condition, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 2
    }
    return [bool](& $Condition)
}

$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole('Administrators')
if (-not $isAdmin) { throw "Restart refused: not elevated. Run this from an Administrator PowerShell." }

# --- gate: no job may be in flight -----------------------------------------
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$counter = Join-Path $PSScriptRoot 'inflight_count.py'
$inFlight = & $python $counter (Join-Path $repoRoot 'records.db')
if ($LASTEXITCODE -ne 0) { throw "Restart refused: in-flight check failed: $inFlight" }
if ([int]$inFlight -ne 0) { throw "Restart refused: $inFlight job(s) in flight. Wait for the queue to drain." }
Write-Host "Queue idle."

# --- stop: the task, then every backend python of this repo -----------------
$restartStarted = Get-Date
$oldListener = Get-ListenerProcessId
Write-Host "Old listener on port ${Port}: $(if ($oldListener) { "PID $oldListener" } else { 'none' })"
schtasks /End /TN $TaskName | Out-Null
$survivors = @(Get-BackendPythonProcessIds)
if ($oldListener -and $oldListener -notin $survivors) { $survivors += $oldListener }
foreach ($survivor in $survivors) {
    if (-not (Get-Process -Id $survivor -ErrorAction SilentlyContinue)) { continue }
    $treeRoot = Get-PythonTreeRoot $survivor
    Write-Host "Killing backend python tree (root PID $treeRoot, member PID $survivor)."
    taskkill /F /T /PID $treeRoot 2>&1 | Out-Host
}
if (-not (Wait-Until { -not (Get-ListenerProcessId) -and -not (Get-BackendPythonProcessIds) } $StopTimeoutSeconds)) {
    throw "Port $Port or a backend python is still alive after ${StopTimeoutSeconds}s (listener PID: $(Get-ListenerProcessId)). The old server is stopped or stopping; start it with: schtasks /Run /TN `"$TaskName`""
}
Write-Host "Old backend stopped; port $Port is free."

# --- start and prove a NEW process serves -----------------------------------
schtasks /Run /TN $TaskName | Out-Null
Write-Host "Start requested. Waiting up to ${BootTimeoutSeconds}s for a new listener and a fresh startup line..."
$bootFailure = $null
$booted = Wait-Until {
    $abort = Find-PreflightAbortSince $restartStarted
    if ($abort) { $script:bootFailure = "preflight aborted: $abort"; return $true }
    $listener = Get-ListenerProcessId
    $sinceStart = ((Get-Date) - $restartStarted).TotalSeconds
    # An import error or crash ends the python and then the launcher, so the
    # task leaves 'Running'. The launcher stays alive for the whole boot.
    if (-not $listener -and $sinceStart -gt $TaskStartGraceSeconds) {
        $taskState = (Get-ScheduledTask -TaskName ($TaskName.TrimStart('\'))).State
        if ("$taskState" -ne 'Running' -and -not (Get-BackendPythonProcessIds)) {
            $script:bootFailure = "the task is '$taskState', no backend python runs and nothing listens on port $Port"
            return $true
        }
    }
    if (-not $listener -or $listener -eq $oldListener) { return $false }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listener" -ErrorAction SilentlyContinue
    if (-not $process -or $process.CreationDate -lt $restartStarted) { return $false }
    return [bool](Find-BootLogLineSince 'Application startup complete' $restartStarted)
} $BootTimeoutSeconds
if ($bootFailure) { throw "Backend failed to boot: $bootFailure.`n$(Get-LogTails)" }
if (-not $booted) { throw "No new backend within ${BootTimeoutSeconds}s (listener PID: $(Get-ListenerProcessId)).`n$(Get-LogTails)" }
$newListener = Get-ListenerProcessId
$started = (Get-CimInstance Win32_Process -Filter "ProcessId=$newListener").CreationDate
$health = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 15
if ($health.StatusCode -ne 200) { throw "New backend PID $newListener answered /health with HTTP $($health.StatusCode)." }
$priority = (Get-Process -Id $newListener).BasePriority
Write-Host ("Backend up: new PID {0} (BasePriority {1}), started {2:HH:mm:ss}, boot took {3:N0}s." -f $newListener, $priority, $started, ((Get-Date) - $restartStarted).TotalSeconds)

# --- verify /api/usage (advisory) --------------------------------------------
$key = $env:WSP_API_KEY
if (-not $key) { $key = [Environment]::GetEnvironmentVariable('WSP_API_KEY', 'User') }
if (-not $key) { Write-Warning "WSP_API_KEY is not set. Skipping the /api/usage check."; return }

# Cloudflare answers 403 "error code: 1010" to unrecognised clients, so send a
# browser User-Agent. A bare tool UA fails at the edge, never reaching uvicorn.
$headers = @{
    Authorization = "Bearer $key"
    'User-Agent'  = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
}
try {
    $usage = Invoke-RestMethod -Uri 'https://wsp.kingdom.lv/api/usage' -Headers $headers -TimeoutSec 30
    $usage | Select-Object plan_tier, unlimited, hour_count, hour_limit, daily_minutes_used, daily_minutes_limit | Format-List
    if ($usage.unlimited -ne $true) { Write-Warning "unlimited is not true. Is the key flagged, and did the new usage code load?" }
    if ($null -ne $usage.hour_limit) { Write-Warning "hour_limit is not null. The /api/usage change did not load." }
} catch {
    Write-Warning "Public /api/usage check failed (the backend itself is up): $_"
}
