#Requires -RunAsAdministrator
<#
One-time machine repair for the WhisperX backend port.

Symptom: uvicorn loops on
  [Errno 13] bind on ('0.0.0.0', 8000): [winerror 10013]
with nothing listening on 8000. Windows reserved the port. WinNAT/Hyper-V carve
100-port blocks out of the TCP dynamic port range at boot, and if that range
starts low (this machine shipped 1024/64511) a block can land on 8000. The boot
launcher's preflight kill cannot recover it - no process owns the port.

This resets the dynamic range to the Windows default so blocks land above 49152,
then hands off to ensure-port-8000.ps1 for the persistent reservation.
Routine boots only run ensure-port-8000.ps1; this script is for the one-time
range repair or after a reboot leaves the port blocked anyway.

Side effect: cycling WinNAT/HNS briefly breaks Docker/WSL/Hyper-V NAT networking.
#>
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Show-State($label) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    netsh interface ipv4 show excludedportrange protocol=tcp |
        Select-String -Pattern '^\s*\d+' |
        ForEach-Object {
            $fields = $_.ToString().Trim() -split '\s+'
            if ([int]$fields[0] -le $Port -and [int]$fields[1] -ge $Port) { "  $_   <-- covers $Port" } else { "  $_" }
        }
    netsh interface ipv4 show dynamicport tcp | Select-String 'Start Port|Number of Ports'
}

Show-State 'BEFORE'

$runningServices = @('hns', 'winnat') | Where-Object {
    (Get-Service $_ -ErrorAction SilentlyContinue).Status -eq 'Running'
}

Write-Host "`nStopping: $($runningServices -join ', ')" -ForegroundColor Yellow
foreach ($service in $runningServices) { Stop-Service $service -Force }

Write-Host 'Restoring default TCP/UDP dynamic port range (49152, 16384 ports)' -ForegroundColor Yellow
netsh int ipv4 set dynamicport tcp start=49152 num=16384 | Out-Null
netsh int ipv4 set dynamicport udp start=49152 num=16384 | Out-Null
netsh int ipv6 set dynamicport tcp start=49152 num=16384 | Out-Null
netsh int ipv6 set dynamicport udp start=49152 num=16384 | Out-Null

foreach ($service in ($runningServices | Sort-Object -Descending)) { Start-Service $service }

Write-Host "`nReserving port $Port" -ForegroundColor Yellow
& (Join-Path $scriptDir 'ensure-port-8000.ps1') -Port $Port
if ($LASTEXITCODE -ne 0) {
    Show-State 'AFTER'
    Write-Host "`nPort $Port still blocked. Reboot, then re-run this script." -ForegroundColor Red
    exit 1
}

Show-State 'AFTER'
Write-Host "`nBind test on $Port : OK" -ForegroundColor Green

$task = Get-ScheduledTask | Where-Object {
    ($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -match 'start-server-boot'
} | Select-Object -First 1
if ($task) {
    Write-Host "Restarting task: $($task.TaskPath)$($task.TaskName)" -ForegroundColor Yellow
    Start-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName
} else {
    Write-Host 'Backend scheduled task not found - the 5-min watchdog will pick it up.' -ForegroundColor Yellow
}

Write-Host 'Waiting for /health ...' -NoNewline
foreach ($attempt in 1..60) {
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 3 -UseBasicParsing
        Write-Host " HTTP $($response.StatusCode)" -ForegroundColor Green
        exit 0
    } catch { Write-Host '.' -NoNewline; Start-Sleep -Seconds 5 }
}
Write-Host ' TIMEOUT - check logs\backend-boot.log' -ForegroundColor Red
exit 1
