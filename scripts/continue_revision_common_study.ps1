param([Parameter(Mandatory = $true)][ValidateRange(1, 100000)][int]$MaxRequests)

$ErrorActionPreference = 'Stop'
$taskRepoRoot = Split-Path -Parent $PSScriptRoot
$taskRun = Join-Path $taskRepoRoot 'outputs/revision/r1_common_run_v2'
[System.IO.Directory]::CreateDirectory($taskRun) | Out-Null
Set-Location -LiteralPath $taskRepoRoot
$taskController = $null
try {
    # Một controller duy nhất; khóa tự nhả khi tiến trình đóng.
    $taskController = [System.IO.File]::Open((Join-Path $taskRun 'controller.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $taskLog = Join-Path $taskRun ("worker_{0}.log" -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
    $taskStatusPath = Join-Path $taskRun 'worker_status.json'
    function Set-TaskStatus([string]$phase, [int]$code = 0) {
        @{
            phase = $phase; process_id = $PID; max_requests = $MaxRequests
            updated_at_utc = [DateTime]::UtcNow.ToString('o'); exit_code = $code
            log = [System.IO.Path]::GetFileName($taskLog)
            controller_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        } | ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding utf8
    }
    Set-TaskStatus 'waiting_for_current_smoke'
    $taskReady = $false
    while (-not $taskReady) {
        try {
            $taskProbe = [System.IO.File]::Open((Join-Path $taskRun 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
            $taskProbe.Dispose()
            $taskReady = $true
        } catch [System.IO.IOException] { Start-Sleep -Seconds 10 }
    }
    # Giữ nguyên run identity; không đổi model, protocol hoặc retry vô hạn.
    $env:PYTHONUNBUFFERED = '1'
    Set-TaskStatus 'inference'
    & py -3.13 -X utf8 scripts/run_revision_common_study.py run --max-requests $MaxRequests *> $taskLog
    $taskExit = $LASTEXITCODE
    if ($taskExit -ne 0) {
        Set-TaskStatus 'inference_stopped_requires_review' $taskExit
        exit $taskExit
    }
    Set-TaskStatus 'analysis'
    & py -3.13 -X utf8 scripts/run_revision_common_study.py analyze *>> $taskLog
    $taskExit = $LASTEXITCODE
    if ($taskExit -ne 0) {
        Set-TaskStatus 'analysis_stopped_requires_review' $taskExit
        exit $taskExit
    }
    Set-TaskStatus 'analysis_complete_pending_scientific_review'
} catch {
    if ($taskController) { Set-TaskStatus 'controller_stopped_requires_review' 1 }
    throw
} finally {
    if ($taskController) { $taskController.Dispose() }
}
