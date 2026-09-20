$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location "$Root\backend"
$Python = "$Root\backend\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $Python = "python"
}
& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
