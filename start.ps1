$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run setup.ps1 first.' }
    & '.\.venv\Scripts\python.exe' -m uvicorn server:app --host 127.0.0.1 --port 8000
} finally { Pop-Location }
