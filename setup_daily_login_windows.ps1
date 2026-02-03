# Windows Task Scheduler Setup for Daily Auto-Login
# Run this script as Administrator

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "DAILY AUTO-LOGIN SETUP (WINDOWS)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will create a Windows Task to run auto-login at 9:15 AM (Mon-Fri)"
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$AutoLoginScript = Join-Path $ScriptDir "auto_login.py"

# Check if Python exists
if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python not found at $PythonExe" -ForegroundColor Red
    Write-Host "Make sure virtual environment is created" -ForegroundColor Red
    exit 1
}

# Check if auto_login.py exists
if (-not (Test-Path $AutoLoginScript)) {
    Write-Host "ERROR: auto_login.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "Creating scheduled task..." -ForegroundColor Yellow
Write-Host ""

# Create task action
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $AutoLoginScript -WorkingDirectory $ScriptDir

# Create triggers for Monday to Friday at 9:15 AM
$Triggers = @()

# Monday
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9:15AM
$Triggers += $Trigger

# Tuesday
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 9:15AM
$Triggers += $Trigger

# Wednesday
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At 9:15AM
$Triggers += $Trigger

# Thursday
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At 9:15AM
$Triggers += $Trigger

# Friday
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 9:15AM
$Triggers += $Trigger

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task
$TaskName = "KiteAutoLogin"
$Description = "Automatically generates Kite access token at 9:15 AM on weekdays"

try {
    # Remove existing task if it exists
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    
    # Register new task
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Description $Description -Force
    
    Write-Host ""
    Write-Host "SUCCESS: Scheduled task created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Name: $TaskName" -ForegroundColor Cyan
    Write-Host "Schedule: 9:15 AM, Monday to Friday" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Useful commands:" -ForegroundColor Yellow
    Write-Host "  View task: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Run now: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Disable: Disable-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Remove: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "Test auto-login now? (y/n): " -NoNewline -ForegroundColor Yellow
    $response = Read-Host
    
    if ($response -eq 'y' -or $response -eq 'Y') {
        Write-Host ""
        Write-Host "Running auto-login test..." -ForegroundColor Yellow
        & $PythonExe $AutoLoginScript
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "SUCCESS: Auto-login test passed!" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "ERROR: Auto-login test failed!" -ForegroundColor Red
            Write-Host "Check TOTP configuration in .env file" -ForegroundColor Yellow
        }
    }
    
} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to create scheduled task" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure you run this script as Administrator" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
