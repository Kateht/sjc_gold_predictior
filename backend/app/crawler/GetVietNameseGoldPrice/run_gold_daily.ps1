param(
    [ValidateSet("update-backfill", "pipeline")]
    [string]$Mode = "update-backfill",

    [string]$Start = "26/03/2026"
)

Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "Running gold CLI mode: $Mode"

if ($Mode -eq "pipeline") {
    & $pythonExe "gold_cli.py" "pipeline" "--start" $Start
} else {
    & $pythonExe "gold_cli.py" "update-backfill" "--start" $Start
}
