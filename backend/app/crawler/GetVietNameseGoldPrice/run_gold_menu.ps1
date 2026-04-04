Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe "gold_cli.py"