$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$RawDir = Join-Path $PackageRoot "data\external\mtsamples\raw"
$CsvPath = Join-Path $RawDir "mtsamples.csv"

New-Item -ItemType Directory -Force -Path $RawDir | Out-Null

if (Test-Path $CsvPath) {
    throw "Refusing to overwrite existing source file: $CsvPath. Inspect or back it up first."
}

$KaggleCommand = Get-Command kaggle -ErrorAction SilentlyContinue
if (-not $KaggleCommand) {
    Write-Host "Kaggle CLI is not available in this PowerShell session. No software was installed."
    Write-Host "Manual download: https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data"
    Write-Host "Sign in to Kaggle, download and extract the ZIP, then copy the original mtsamples.csv to:"
    Write-Host "  $CsvPath"
    Write-Host "After copying the file, run: python .\scripts\analyze_mtsamples.py"
    return
}

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mirai-mtsamples-" + [guid]::NewGuid().ToString("N"))
$DownloadDir = Join-Path $TempRoot "download"
$ExtractDir = Join-Path $TempRoot "extracted"
New-Item -ItemType Directory -Force -Path $DownloadDir, $ExtractDir | Out-Null

try {
    Write-Host "Downloading Kaggle dataset to a temporary directory. Credentials will not be displayed."
    & $KaggleCommand.Source datasets download -d "tboyle10/medicaltranscriptions" -p $DownloadDir
    if ($LASTEXITCODE -ne 0) {
        throw "Kaggle CLI download failed. Check your Kaggle access/authentication locally, or use the manual browser download instructions above. No credentials should be pasted into chat."
    }

    $Archives = @(Get-ChildItem -Path $DownloadDir -Filter "*.zip" -File)
    if ($Archives.Count -ne 1) {
        throw "Expected exactly one downloaded ZIP archive; found $($Archives.Count). Inspect the temporary download before retrying."
    }

    Expand-Archive -LiteralPath $Archives[0].FullName -DestinationPath $ExtractDir
    $Candidates = @(Get-ChildItem -Path $ExtractDir -Filter "mtsamples.csv" -File -Recurse)
    if ($Candidates.Count -ne 1) {
        throw "Expected exactly one mtsamples.csv in the archive; found $($Candidates.Count). No source file was copied into the raw directory."
    }

    Copy-Item -LiteralPath $Candidates[0].FullName -Destination $CsvPath
    $ArchiveDestination = Join-Path $RawDir "medicaltranscriptions-source.zip"
    if (Test-Path $ArchiveDestination) {
        Remove-Item -LiteralPath $CsvPath -Force
        throw "Refusing to overwrite existing archive: $ArchiveDestination. No final download was retained. Inspect existing data first."
    }
    Copy-Item -LiteralPath $Archives[0].FullName -Destination $ArchiveDestination

    Write-Host "Kaggle source files are ready:"
    Write-Host "  CSV: $CsvPath"
    Write-Host "  Archive: $ArchiveDestination"
    Write-Host "Next run: python .\scripts\analyze_mtsamples.py"
}
finally {
    if (Test-Path $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
