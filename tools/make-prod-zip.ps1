# Create production zip with forward-slash entries (Linux-friendly).
# Usage: powershell -NoProfile -File tools/make-prod-zip.ps1 -StageDir <dir> -ZipPath <file>

param(
    [Parameter(Mandatory = $true)][string]$StageDir,
    [Parameter(Mandatory = $true)][string]$ZipPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $StageDir)) {
    throw "Stage directory not found: $StageDir"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

$stageFull = (Resolve-Path -LiteralPath $StageDir).Path.TrimEnd('\', '/')
$zip = [System.IO.Compression.ZipFile]::Open(
    $ZipPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)

try {
    $files = Get-ChildItem -LiteralPath $stageFull -Recurse -File
    foreach ($file in $files) {
        $rel = $file.FullName.Substring($stageFull.Length).TrimStart('\', '/').Replace('\', '/')
        $entryName = "worldcup-predict/$rel"
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        )
    }
}
finally {
    $zip.Dispose()
}

Write-Host "[OK] ZIP created: $ZipPath ($($files.Count) files)"
