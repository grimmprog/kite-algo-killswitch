#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Security scanning script for the Web Trading Platform.
.DESCRIPTION
    Runs Bandit (Python SAST) and documents OWASP ZAP configuration for API scanning.
    Use this script as part of CI/CD or manual security audits.
.EXAMPLE
    .\scripts\security_scan.ps1
    .\scripts\security_scan.ps1 -Severity "medium"
    .\scripts\security_scan.ps1 -OutputFormat "json" -OutputFile "reports/bandit_report.json"
#>

param(
    [ValidateSet("low", "medium", "high")]
    [string]$Severity = "medium",

    [ValidateSet("txt", "json", "html", "csv")]
    [string]$OutputFormat = "txt",

    [string]$OutputFile = "",

    [switch]$FixMode,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Security Scan - Web Trading Platform" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- Check Prerequisites ---
Write-Host "[1/4] Checking prerequisites..." -ForegroundColor Yellow

try {
    $banditVersion = python -m bandit --version 2>&1
    Write-Host "  Bandit found: $banditVersion" -ForegroundColor Green
} catch {
    Write-Host "  Bandit not found. Installing..." -ForegroundColor Red
    pip install bandit
}

# --- Run Bandit SAST Scanner ---
Write-Host ""
Write-Host "[2/4] Running Bandit Static Analysis..." -ForegroundColor Yellow
Write-Host "  Target: src/" -ForegroundColor Gray
Write-Host "  Severity: $Severity and above" -ForegroundColor Gray
Write-Host "  Config: .bandit" -ForegroundColor Gray
Write-Host ""

$severityFlag = switch ($Severity) {
    "low"    { "-l" }
    "medium" { "-ll" }
    "high"   { "-lll" }
}

$banditArgs = @(
    "-m", "bandit",
    "-r", "src/",
    $severityFlag,
    "-f", $OutputFormat
)

if ($OutputFile) {
    $reportDir = Split-Path -Parent $OutputFile
    if ($reportDir -and -not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    $banditArgs += @("-o", $OutputFile)
    Write-Host "  Output: $OutputFile" -ForegroundColor Gray
}

if ($Verbose) {
    $banditArgs += @("-v")
}

Push-Location $ProjectRoot
try {
    $ErrorActionPreference = "Continue"
    $result = & python @banditArgs 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"

    if ($OutputFile) {
        Write-Host "  Report saved to: $OutputFile" -ForegroundColor Green
    } else {
        Write-Output $result
    }

    Write-Host ""
    if ($exitCode -eq 0) {
        Write-Host "  [PASS] No issues found at severity '$Severity' or above." -ForegroundColor Green
    } elseif ($exitCode -eq 1) {
        Write-Host "  [WARN] Security issues found. Review output above." -ForegroundColor Yellow
    } else {
        Write-Host "  [ERROR] Bandit encountered an error (exit code: $exitCode)." -ForegroundColor Red
    }
} finally {
    Pop-Location
}

# --- OWASP ZAP Info ---
Write-Host ""
Write-Host "[3/4] OWASP ZAP Configuration..." -ForegroundColor Yellow
Write-Host "  ZAP scan config: tests/security/zap_scan_config.yaml" -ForegroundColor Gray
Write-Host "  Note: ZAP requires a running API server. Run separately with:" -ForegroundColor Gray
Write-Host "    docker run -t ghcr.io/zaproxy/zaproxy:stable zap-api-scan.py \" -ForegroundColor Gray
Write-Host "      -t http://localhost:8000/openapi.json -f openapi \" -ForegroundColor Gray
Write-Host "      -c tests/security/zap_scan_config.yaml" -ForegroundColor Gray

# --- Summary ---
Write-Host ""
Write-Host "[4/4] Summary" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Bandit SAST:     Completed" -ForegroundColor Green
Write-Host "  OWASP ZAP DAST:  Config ready (requires live server)" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

exit $exitCode
