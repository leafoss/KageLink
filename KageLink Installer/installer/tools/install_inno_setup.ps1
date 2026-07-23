$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Fallback usado somente quando winget não está disponível ou falhou.
# URL oficial atualmente publicada pelo projeto Inno Setup 6.
$downloadUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
$installerPath = Join-Path $env:TEMP "KageLink_innosetup-6.7.3.exe"

Write-Host "Downloading the official Inno Setup installer..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath -UseBasicParsing

if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "The Inno Setup installer was not downloaded."
}

Write-Host "Checking the Windows Authenticode signature..."
$signature = Get-AuthenticodeSignature -LiteralPath $installerPath

if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    throw "The downloaded installer does not have a valid digital signature."
}

$subject = [string]$signature.SignerCertificate.Subject
if ($subject -notmatch "Pyrsys B\.V\.") {
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    throw "Unexpected digital signer: $subject"
}

Write-Host "Valid signature confirmed: $subject"
Write-Host "Installing Inno Setup..."

$arguments = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"
$process = Start-Process `
    -FilePath $installerPath `
    -ArgumentList $arguments `
    -Verb RunAs `
    -Wait `
    -PassThru

$exitCode = $process.ExitCode
Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue

if ($exitCode -ne 0) {
    throw "Inno Setup installer returned exit code $exitCode."
}

Write-Host "Inno Setup installed successfully."
exit 0
