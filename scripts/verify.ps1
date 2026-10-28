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
Invoke-Checked "pytest" { python -m pytest -q }
Invoke-Checked "ruff" { python -m ruff check backend }

Set-Location (Join-Path $root "frontend")
Invoke-Checked "typecheck" { npm run typecheck }
Invoke-Checked "frontend build" { npm run build }

Set-Location $root
Invoke-Checked "reproducibility verification" {
    python -m yottaflex.cli verify --profile small --seed 20261022
}

Write-Host ""
Write-Host "Verification complete."
