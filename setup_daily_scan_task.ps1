# Setup Windows Task Scheduler for daily job scanning
# Run this script as Administrator

$TaskName = "JobAgent-DailyScan"
$PythonPath = "C:\Program Files\Python312\python.exe"
$ScriptPath = "C:\Users\ClawAdmin\.qclaw\workspace\job-agent\daily_scan_and_push.py"
$WorkDir = "C:\Users\ClawAdmin\.qclaw\workspace\job-agent"

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Task '$TaskName' already exists. Removing..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $ScriptPath `
    -WorkingDirectory $WorkDir

# Create trigger (daily at 9:00 AM)
$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "9:00 AM"

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Register task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily job scanning and GitHub auto-push"

Write-Host ""
Write-Host "✓ Task created: $TaskName"
Write-Host "✓ Schedule: Daily at 9:00 AM"
Write-Host "✓ Script: $ScriptPath"
Write-Host ""
Write-Host "To test manually: schtasks /run /tn JobAgent-DailyScan"
Write-Host "To view task: taskschd.msc"
