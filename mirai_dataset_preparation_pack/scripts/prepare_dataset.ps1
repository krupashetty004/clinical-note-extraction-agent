$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $PSScriptRoot
$CsvPath = Join-Path $PackageRoot "data\external\mtsamples\raw\mtsamples.csv"

if (-not (Test-Path $CsvPath)) {
    & (Join-Path $PSScriptRoot "download_mtsamples.ps1")
    if (-not (Test-Path $CsvPath)) {
        throw "Dataset download is not complete. Follow the browser download instructions printed above, then rerun this script."
    }
}

python (Join-Path $PSScriptRoot "analyze_mtsamples.py")
if ($LASTEXITCODE -ne 0) {
    throw "Dataset analysis failed. Review the reported error; source files were not deleted."
}

Write-Host "Dataset preparation and quality analysis completed. Review reports\dataset_quality_report.md before using records for evaluation."
Write-Host "Note: the 100-record annotation file is an unannotated queue, not gold-labelled evaluation data."
