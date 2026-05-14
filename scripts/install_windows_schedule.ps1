#Requires -Version 5.1
<#
  註冊兩個「目前使用者」排程工作（台北時間以本機時鐘為準，請將 Windows 設為 UTC+8）：
    - 16:30  抓取 + 若有變更則 git commit / push
    - 17:00  僅發送 Telegram（--send-only）

  移除：.\scripts\install_windows_schedule.ps1 -Unregister
#>
param(
    [switch]$Unregister
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FetchPs1 = Join-Path $PSScriptRoot "daily_fetch_commit_push.ps1"
$SendPs1 = Join-Path $PSScriptRoot "daily_send_only.ps1"
$Pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$taskFetch = "00981A-ETF-FetchPush"
$taskSend = "00981A-ETF-SendTelegram"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskFetch -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskSend -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] 已嘗試移除排程工作：$taskFetch、$taskSend"
    exit 0
}

if (-not (Test-Path -LiteralPath $FetchPs1)) { throw "找不到 $FetchPs1" }
if (-not (Test-Path -LiteralPath $SendPs1)) { throw "找不到 $SendPs1" }

$argFetch = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$FetchPs1`""
$argSend = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$SendPs1`""

$actionFetch = New-ScheduledTaskAction -Execute $Pwsh -Argument $argFetch -WorkingDirectory $RepoRoot
$actionSend = New-ScheduledTaskAction -Execute $Pwsh -Argument $argSend -WorkingDirectory $RepoRoot

$trFetch = New-ScheduledTaskTrigger -Daily -At "4:30pm"
$trSend = New-ScheduledTaskTrigger -Daily -At "5:00pm"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskFetch -Action $actionFetch -Trigger $trFetch `
    -Settings $settings -Principal $principal `
    -Description "00981A：每日 16:30 抓取持股，若有 JSON 變更則 commit 並 push" -Force

Register-ScheduledTask -TaskName $taskSend -Action $actionSend -Trigger $trSend `
    -Settings $settings -Principal $principal `
    -Description "00981A：每日 17:00 讀取 holdings 並發送 Telegram" -Force

Write-Host "[OK] 已註冊排程工作（以本機時區的 16:30 / 17:00 為準）："
Write-Host "    - $taskFetch"
Write-Host "    - $taskSend"
Write-Host ""
Write-Host "Note: GitHub Actions plus local schedule may duplicate Telegram; pick one if needed."
$self = Join-Path $PSScriptRoot "install_windows_schedule.ps1"
Write-Host ("To remove tasks: powershell -NoProfile -ExecutionPolicy Bypass -File ""{0}"" -Unregister" -f $self)
