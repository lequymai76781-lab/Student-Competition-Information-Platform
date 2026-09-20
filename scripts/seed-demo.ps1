$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location "$Root\backend"
$Python = "$Root\backend\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $Python = "python"
}
& $Python -m scripts.seed_demo_data
