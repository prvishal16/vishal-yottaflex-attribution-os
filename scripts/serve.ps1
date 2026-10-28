param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendIndex = Join-Path $root "frontend\dist\index.html"

Set-Location $root

if (-not (Test-Path -LiteralPath $frontendIndex)) {
    Set-Location (Join-Path $root "frontend")
    npm run build
    Set-Location $root
}

python -m yottaflex.cli serve --host $BindHost --port $Port
