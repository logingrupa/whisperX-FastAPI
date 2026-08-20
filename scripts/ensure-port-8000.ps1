<#
Guarantees TCP $Port is bindable before the backend starts.

WinNAT/Hyper-V carve 100-port blocks out of the TCP dynamic range at boot. If a
block covers the backend port, uvicorn dies with WinError 10013 and no process
owns the port, so killing PIDs cannot recover it - the watchdog just relaunches
into the same failure every 5 minutes.

The permanent guard is a persistent administered exclusion on the port. This
script verifies that reservation is still in place and re-creates it if some
future Windows update or netsh reset drops it. Healing needs Administrator;
running as SYSTEM (the Scheduled Task) qualifies.

Exit 0 = port bindable. Exit 1 = still blocked, caller should not bother starting.
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

if ($ourReservation -and -not $foreignBlock) { exit 0 }

Write-Output "PORT $Port IS OS-RESERVED - Windows took the port, no process owns it."
foreach ($range in $covering) {
    Write-Output ("  blocking range {0}-{1}{2}" -f $range.Start, $range.End, $(if ($range.Administered) { ' (administered)' } else { ' (WinNAT dynamic)' }))
}
if (-not $ourReservation) { Write-Output "  persistent reservation for $Port is MISSING" }

$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Output "  cannot self-heal without Administrator - run scripts\fix-port-8000-exclusion.ps1 elevated"
    exit 1
}

Write-Output '  self-healing: cycling hns/winnat and re-reserving the port'
$runningServices = @('hns', 'winnat') | Where-Object {
    (Get-Service $_ -ErrorAction SilentlyContinue).Status -eq 'Running'
}
foreach ($service in $runningServices) { Stop-Service $service -Force }
netsh int ipv4 add excludedportrange protocol=tcp startport=$Port numberofports=1 store=persistent | Out-Null
foreach ($service in ($runningServices | Sort-Object -Descending)) { Start-Service $service }

if (Test-PortBindable $Port) {
    Write-Output "  port $Port recovered"
    exit 0
}
Write-Output "  port $Port STILL BLOCKED after self-heal - reboot, then run scripts\fix-port-8000-exclusion.ps1"
exit 1
