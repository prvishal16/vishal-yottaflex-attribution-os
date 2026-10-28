$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

Set-Location $root
Invoke-Checked "Python install" { python -m pip install -e ".[dev]" }

Set-Location (Join-Path $root "frontend")
Invoke-Checked "npm install" { npm install }
Invoke-Checked "frontend build" { npm run build }

Set-Location $root
Invoke-Checked "dataset generation" {
    python -m yottaflex.cli generate --profile small
}

Write-Host ""
Write-Host "Bootstrap complete. Start the console with: .\scripts\serve.ps1"
