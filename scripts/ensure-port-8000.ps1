<#
Guarantees TCP $Port is free before the backend starts. Two ways it can be taken:

1. Windows reserved it. WinNAT/Hyper-V carve 100-port blocks out of the TCP
   dynamic range at boot; a block covering the port makes uvicorn die with
   WinError 10013 and no process owns it, so killing PIDs cannot recover it.
   The permanent guard is a persistent administered exclusion, re-created here
   if a Windows update or netsh reset ever drops it. Healing needs Administrator;
   running as SYSTEM (the Scheduled Task) qualifies.

2. A stale server still holds it - an orphan the launcher's kill missed, which
   otherwise surfaces as a bare WinError 10048.

Exit 0 = port bindable. Exit 1 = blocked, with the reason named; the caller
should abort rather than launch into an unexplained bind error.
#>
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'

function Get-CoveringRanges([int]$targetPort) {
    netsh interface ipv4 show excludedportrange protocol=tcp |
        Select-String -Pattern '^\s*\d+' |
        ForEach-Object {
            $line = $_.ToString()
            $fields = $line.Trim() -split '\s+'
            [pscustomobject]@{
                Start        = [int]$fields[0]
                End          = [int]$fields[1]
                Administered = $line -match '\*'
            }
        } |
        Where-Object { $_.Start -le $targetPort -and $_.End -ge $targetPort }
}

function Test-PortBindable([int]$targetPort) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $targetPort)
    try { $listener.Start(); $listener.Stop(); return $true } catch { return $false }
}

$covering = @(Get-CoveringRanges $Port)
$ourReservation = $covering | Where-Object { $_.Administered -and $_.Start -eq $Port -and $_.End -eq $Port }
$foreignBlock = $covering | Where-Object { $_.Start -ne $Port -or $_.End -ne $Port }
$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (Test-PortBindable $Port) {
    if ($ourReservation) { exit 0 }

    Write-Output "port $Port is free but has no persistent reservation - WinNAT could claim it on the next boot"
    if (-not $isAdmin) {
        Write-Output '  needs Administrator to re-reserve - run scripts\fix-port-8000-exclusion.ps1 elevated'
        exit 0
    }
    netsh int ipv4 add excludedportrange protocol=tcp startport=$Port numberofports=1 store=persistent | Out-Null
    Write-Output "  reservation for $Port restored"
    exit 0
}

if ($foreignBlock) {
    Write-Output "PORT $Port IS OS-RESERVED - Windows took the port, no process owns it."
    foreach ($range in $foreignBlock) {
        Write-Output ("  blocking range {0}-{1}{2}" -f $range.Start, $range.End,
            $(if ($range.Administered) { ' (administered)' } else { ' (WinNAT dynamic)' }))
    }
    if (-not $isAdmin) {
        Write-Output '  cannot self-heal without Administrator - run scripts\fix-port-8000-exclusion.ps1 elevated'
        exit 1
    }

    Write-Output '  self-healing: cycling hns/winnat and re-reserving the port'
    $runningServices = @('hns', 'winnat') | Where-Object {
        (Get-Service $_ -ErrorAction SilentlyContinue).Status -eq 'Running'
    }
    foreach ($service in $runningServices) { Stop-Service $service -Force }
    netsh int ipv4 add excludedportrange protocol=tcp startport=$Port numberofports=1 store=persistent | Out-Null
    foreach ($service in ($runningServices | Sort-Object -Descending)) { Start-Service $service }

    if (Test-PortBindable $Port) { Write-Output "  port $Port recovered"; exit 0 }
    Write-Output "  port $Port STILL BLOCKED - reboot, then run scripts\fix-port-8000-exclusion.ps1 elevated"
    exit 1
}

Write-Output "PORT $Port IS NOT BINDABLE."
$owners = @((Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).OwningProcess) |
    Select-Object -Unique | Where-Object { $_ }
foreach ($owningPid in $owners) {
    $owningProcess = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
    Write-Output ("  held by PID {0} ({1}) - the preflight kill missed it" -f $owningPid,
        $(if ($owningProcess) { $owningProcess.ProcessName } else { 'unknown' }))
}
if (-not $owners) { Write-Output '  no owning process and no foreign exclusion - unexplained; check the socket state' }
exit 1
