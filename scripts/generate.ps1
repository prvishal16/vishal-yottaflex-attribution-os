param(
    [ValidateSet("small", "demo", "full")]
    [string]$Profile = "small",
    [int]$Seed = 20261022,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$cliArgs = @("generate", "--profile", $Profile, "--seed", $Seed)

if ($Strict) {
    $cliArgs += "--strict"
}

Set-Location $root
python -m yottaflex.cli @cliArgs
if ($LASTEXITCODE -ne 0) {
    throw "Dataset generation failed with exit code $LASTEXITCODE."
}
