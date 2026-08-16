# Verify production zip contains critical backend modules.
# Usage: powershell -NoProfile -File tools/verify-prod-zip.ps1 -ZipPath <file>

param(
    [Parameter(Mandatory = $true)][string]$ZipPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "ZIP not found: $ZipPath"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $names = @(
        $zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') }
    )

    $needExact = @(
        "worldcup-predict/backend/db/__init__.py",
        "worldcup-predict/backend/alembic/env.py",
        "worldcup-predict/backend/main.py",
        "worldcup-predict/install.sh",
        "worldcup-predict/install.bat",
        "worldcup-predict/install.ps1",
        "worldcup-predict/start-prod.sh",
        "worldcup-predict/stop-prod.sh",
        "worldcup-predict/start-prod.bat",
        "worldcup-predict/stop-prod.bat",
        "worldcup-predict/start-prod.ps1",
        "worldcup-predict/stop-prod.ps1"
    )
    foreach ($n in $needExact) {
        if ($names -notcontains $n) {
            throw "ZIP missing required entry: $n"
        }
    }

    $needPrefix = @(
        "worldcup-predict/backend/api/",
        "worldcup-predict/backend/service/",
        "worldcup-predict/backend/alembic/"
    )
    foreach ($p in $needPrefix) {
        $hit = $names | Where-Object { $_.StartsWith($p) } | Select-Object -First 1
        if (-not $hit) {
            throw "ZIP missing required prefix: $p"
        }
    }

    $backendCount = @($names | Where-Object { $_.StartsWith("worldcup-predict/backend/") }).Count
    if ($backendCount -lt 50) {
        throw "ZIP backend entry count too low: $backendCount (expected >= 50)"
    }

    Write-Host "[OK] ZIP verified: $backendCount backend entries, $($names.Count) total"
}
finally {
    $zip.Dispose()
}
