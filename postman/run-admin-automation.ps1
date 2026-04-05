param(
  [string]$CollectionRelativePath = "postman/gold-prediction-api.postman_collection.json",
  [string]$EnvironmentRelativePath = "postman/gold-prediction-local.postman_environment.json",
  [string]$FolderName = "Admin"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$collectionPath = Resolve-Path (Join-Path $repoRoot $CollectionRelativePath)
$environmentPath = Resolve-Path (Join-Path $repoRoot $EnvironmentRelativePath)
$reportDir = Join-Path $repoRoot "postman/reports"
$reportPath = Join-Path $reportDir "admin-automation.junit.xml"

if (-not (Test-Path $reportDir)) {
  New-Item -ItemType Directory -Path $reportDir | Out-Null
}

Set-Location $repoRoot

npx --yes newman@6.2.1 run "$collectionPath" `
  -e "$environmentPath" `
  --folder "$FolderName" `
  --bail `
  --reporters "cli,junit" `
  --reporter-junit-export "$reportPath"

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Admin automation tests passed."
Write-Host "JUnit report: $reportPath"
