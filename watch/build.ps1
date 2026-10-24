param(
    [string]$Device = "fenix7pro",
    [string]$HaUrl,
    [string]$Out,
    [string]$Sdk = $env:CIQ_SDK,
    [string]$Key = $env:CIQ_KEY,
    [string]$Jdk = $env:CIQ_JDK,
    [switch]$Run,
    [switch]$Seed
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Toolchain locations. Set CIQ_SDK / CIQ_KEY / CIQ_JDK in your environment (or
# pass -Sdk / -Key / -Jdk) to build on your own machine; the fallbacks are just
# one developer's layout. The signing key is personal to each developer — bring
# your own Connect IQ developer_key.der, it is never committed.
if (-not $Sdk) { $Sdk = "D:\LocalAI\Tools\ConnectIQ\sdk-9.2.0" }
if (-not $Key) { $Key = "D:\LocalAI\Tools\ConnectIQ\keys\developer_key.der" }
if (-not $Jdk) { $Jdk = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot\bin" }
$env:Path = "$Jdk;$env:Path"

# The shipped app carries NO credentials: the user enters the URL and token on
# the phone (Garmin Connect -> ChefsTemp -> Settings) and the app caches them on
# the watch. -Seed bakes your own values (from secrets/, git-ignored) as the
# property defaults, for the simulator or a personal pre-filled build only. The
# output lives under build/ which is git-ignored, so no token reaches the repo.
if ($Seed) {
    $token = (Get-Content "$root\secrets\ha_token.txt" -Raw).Trim()
    if (-not $HaUrl) {
        if (Test-Path "$root\secrets\ha_url.txt") {
            $HaUrl = (Get-Content "$root\secrets\ha_url.txt" -Raw).Trim()
        } else {
            throw "Seed build needs a URL: pass -HaUrl or create secrets\ha_url.txt"
        }
    }
    $url = $HaUrl
} else {
    $token = ""
    $url = ""
}
$gen = "$root\build\generated\properties"
New-Item -ItemType Directory -Force $gen | Out-Null
$xml = @"
<properties>
    <property id="haUrl" type="string">$url</property>
    <property id="haToken" type="string">$token</property>
</properties>
"@
[IO.File]::WriteAllText("$gen\properties.xml", $xml)

if (-not $Out) { $Out = "$root\build\ChefsTemp.prg" }
$outDir = Split-Path -Parent $Out
if ($outDir) { New-Item -ItemType Directory -Force $outDir | Out-Null }
& "$Sdk\bin\monkeyc.bat" -f "$root\monkey.jungle" -d $Device -o $Out -y $Key -w
if ($LASTEXITCODE -ne 0) { throw "monkeyc failed" }
Write-Host "Built $Out"

if ($Run) {
    Start-Process "$Sdk\bin\simulator.exe"
    Start-Sleep -Seconds 4
    & "$Sdk\bin\monkeydo.bat" $Out $Device
}
