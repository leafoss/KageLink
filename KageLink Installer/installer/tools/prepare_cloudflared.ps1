$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Version = "2026.7.2"
$Url = "https://github.com/cloudflare/cloudflared/releases/download/2026.7.2/cloudflared-windows-amd64.exe"
$ExpectedSha256 = "cdb5d4432f6ae1595654a692a51308b69d2bf7af961f5578d9391837cf072df9"
$OutputDir = Join-Path $PSScriptRoot "..\payload"
$Output = Join-Path $OutputDir "cloudflared.exe"
$Temporary = Join-Path $OutputDir "cloudflared.download.exe"

function Move-FileWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination,

        [int]$MaximumAttempts = 20,
        [int]$DelayMilliseconds = 500
    )

    for ($Attempt = 1; $Attempt -le $MaximumAttempts; $Attempt++) {
        try {
            Move-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
            return
        }
        catch {
            if ($Attempt -eq $MaximumAttempts) {
                throw
            }

            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$LegacyTemporary = "$Output.download"
foreach ($Candidate in @($LegacyTemporary, $Temporary)) {
    if (Test-Path -LiteralPath $Candidate) {
        Remove-Item -LiteralPath $Candidate -Force -ErrorAction SilentlyContinue
    }
}

if (Test-Path -LiteralPath $Output) {
    $Current = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Current -eq $ExpectedSha256) {
        Write-Host "cloudflared $Version already downloaded and verified."
        exit 0
    }
    Remove-Item -LiteralPath $Output -Force
}

Write-Host "Downloading cloudflared $Version..."
Invoke-WebRequest -Uri $Url -OutFile $Temporary -UseBasicParsing

$Actual = (Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $ExpectedSha256) {
    Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
    throw "cloudflared SHA-256 verification failed. Expected $ExpectedSha256, received $Actual."
}

$Header = [System.IO.File]::ReadAllBytes($Temporary)
if (($Header.Length -lt 2) -or ($Header[0] -ne 0x4D) -or ($Header[1] -ne 0x5A)) {
    Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
    throw "The downloaded cloudflared file is not a valid Windows executable."
}

# Move before executing the binary. Windows Defender or another process may keep
# a recently executed temporary .exe locked briefly, preventing an immediate rename.
Move-FileWithRetry -Source $Temporary -Destination $Output

$VersionOutput = & "$Output" --version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0 -or $VersionOutput -notmatch [regex]::Escape($Version)) {
    Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
    throw "Unexpected cloudflared version. Expected $Version. Received: $VersionOutput"
}

Set-Content `
    -LiteralPath (Join-Path $OutputDir "cloudflared.sha256") `
    -Value $Actual `
    -Encoding ASCII

Write-Host "cloudflared $Version downloaded, version-checked and SHA-256 verified."
