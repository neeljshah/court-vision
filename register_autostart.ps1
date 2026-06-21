<#
.SYNOPSIS
    Build / remove the Windows autostart task that brings the whole stack up on
    power-on. IDEMPOTENT + REVERSIBLE. Does NOT register anything unless you pass
    -Register; the default is a safe -DryRun preview.

.DESCRIPTION
    Registering a "run the whole stack on every boot" Scheduled Task is a
    DELIBERATE GO-LIVE -- it is reserved for the human. This script BUILDS and
    TESTS that wiring but the default action only PREVIEWS it. You must pass
    -Register explicitly to actually create the task; -Unregister removes it.

    What the task does when registered (by the human, later):
      * At user logon (and after a power-on that reaches logon), runs the OUTER
        WATCHDOG (watchdog_autostart.ps1), which keeps boot.ps1's supervisor
        alive: if the supervisor process dies, the watchdog re-runs boot.ps1.
      * boot.ps1 itself runs the M10 governance preflight FIRST (exit 0 or it
        refuses real-money eligibility), then hands the stack to the supervisor
        (readiness-gated + auto-restart). Real money stays default-DENY.

    SAFETY: this script never starts the stack, never flips a flag, never
    enables real money. It only creates/removes/previews a Scheduled Task entry.

.PARAMETER DryRun
    (default) Print exactly what WOULD be registered -- the task name, trigger,
    action, and the schtasks/Register-ScheduledTask command -- and exit. Nothing
    is created.
.PARAMETER Register
    Actually create the Scheduled Task (idempotent: replaces an existing one of
    the same name). THIS IS THE HUMAN GO-LIVE STEP.
.PARAMETER Unregister
    Remove the Scheduled Task if present (idempotent: no error if absent).
.PARAMETER TaskName
    Scheduled Task name (default: "NBA-AI-Stack-Autostart").
.PARAMETER NoUI
    Bake -NoUI into the boot command (headless backend profile).

.EXAMPLE
    .\register_autostart.ps1
    # safe preview (default) -- shows the task it WOULD create; creates nothing.

.EXAMPLE
    .\register_autostart.ps1 -Register
    # THE HUMAN GO-LIVE COMMAND -- creates the logon autostart task.

.EXAMPLE
    .\register_autostart.ps1 -Unregister
    # removes the autostart task; power-on no longer brings the stack up.
#>
[CmdletBinding(DefaultParameterSetName = "DryRun")]
param(
    [Parameter(ParameterSetName = "DryRun")]      [switch]$DryRun,
    [Parameter(ParameterSetName = "Register")]    [switch]$Register,
    [Parameter(ParameterSetName = "Unregister")]  [switch]$Unregister,
    [string]$TaskName = "NBA-AI-Stack-Autostart",
    [switch]$NoUI
)

$ErrorActionPreference = "Stop"
$ROOT     = "C:\Users\neelj\nba-ai-system"
$WATCHDOG = Join-Path $ROOT "watchdog_autostart.ps1"
$bootFlag = if ($NoUI) { " -NoUI" } else { "" }

# The action: launch the outer watchdog (hidden), which owns boot.ps1 + restart.
$psExe = (Get-Command powershell.exe).Source
$actionArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WATCHDOG`"$bootFlag"

function Show-Plan {
    Write-Output ""
    Write-Output "NBA-AI autostart -- DRY RUN (nothing registered)"
    Write-Output "================================================"
    Write-Output "Task name : $TaskName"
    Write-Output "Trigger   : AtLogOn (current user); survives power-on -> logon"
    Write-Output "Action    : $psExe $actionArgs"
    Write-Output "Watchdog  : $WATCHDOG  (keeps boot.ps1's supervisor alive)"
    Write-Output "Governance: boot.ps1 runs M10 preflight FIRST (exit 0 or refuses)"
    Write-Output "Real money: stays default-DENY (human flip + signed token only)"
    Write-Output ""
    Write-Output "Equivalent command that -Register would run:"
    Write-Output "  Register-ScheduledTask -TaskName '$TaskName' -Trigger (logon) ``"
    Write-Output "    -Action (powershell -File watchdog_autostart.ps1$bootFlag) ``"
    Write-Output "    -RunLevel Limited -Force"
    Write-Output ""
    if (-not (Test-Path $WATCHDOG)) {
        Write-Output "NOTE: watchdog_autostart.ps1 not found at $WATCHDOG"
    } else {
        Write-Output "OK: watchdog_autostart.ps1 present."
    }
    Write-Output ""
    Write-Output "To ACTIVATE (human go-live): .\register_autostart.ps1 -Register"
    Write-Output "To remove                  : .\register_autostart.ps1 -Unregister"
}

function Register-Task {
    if (-not (Test-Path $WATCHDOG)) {
        throw "watchdog_autostart.ps1 missing at $WATCHDOG -- refusing to register."
    }
    $action  = New-ScheduledTaskAction -Execute $psExe -Argument $actionArgs -WorkingDirectory $ROOT
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Settings $settings -RunLevel Limited -Force -ErrorAction Stop | Out-Null
    } catch {
        throw "Registration FAILED: $($_.Exception.Message) -- this step needs an ELEVATED PowerShell (right-click PowerShell -> Run as administrator), then re-run: .\register_autostart.ps1 -Register"
    }
    # Belt-and-suspenders: the CIM error can surface non-terminating, so confirm the
    # task actually exists before claiming success (never print a false 'Registered').
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
        throw "Register-ScheduledTask reported no error but task '$TaskName' is ABSENT -- run in an ELEVATED (Administrator) PowerShell and retry."
    }
    Write-Output "Registered Scheduled Task '$TaskName' (AtLogOn -> watchdog -> boot.ps1)."
    Write-Output "Power-on now brings the stack up. Real money stays default-DENY."
    Write-Output "To remove: .\register_autostart.ps1 -Unregister"
}

function Unregister-Task {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Output "Task '$TaskName' not present -- nothing to remove (idempotent)."
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed Scheduled Task '$TaskName'. Power-on no longer auto-starts."
}

switch ($PSCmdlet.ParameterSetName) {
    "Register"   { Register-Task }
    "Unregister" { Unregister-Task }
    default      { Show-Plan }
}
