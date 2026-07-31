[CmdletBinding(SupportsShouldProcess)]
param([string]$Profile = "default")

$Root = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile"
if (Test-Path $Root) {
    if ($PSCmdlet.ShouldProcess($Root, "Remove Navigation Lab profile")) {
        Remove-Item -Recurse -Force $Root
    }
}
