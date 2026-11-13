$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { uv venv .venv --python 3.11; if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' } }
    uv pip install --python '.venv\Scripts\python.exe' --requirement requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} finally { Pop-Location }
