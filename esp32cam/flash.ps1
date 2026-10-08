# Flash de l'ESP32-CAM (Windows).
# Usage : clic droit > "Exécuter avec PowerShell"
#    ou : powershell -ExecutionPolicy Bypass -File flash.ps1 [-Port COM5]
param([string]$Port = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Url  = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
$Fqbn = "esp32:esp32:esp32cam"
$Bin  = Join-Path $PSScriptRoot ".tools"

if (Select-String -Path secrets.h -Pattern "MOT_DE_PASSE|NOM_DU_WIFI" -Quiet) {
  Write-Error "Remplis d'abord secrets.h avec le nom et le mot de passe du Wi-Fi."
}

# 1. arduino-cli (téléchargé localement dans .tools si absent)
$Cli = (Get-Command arduino-cli -ErrorAction SilentlyContinue).Source
if (-not $Cli) {
  $Cli = Join-Path $Bin "arduino-cli.exe"
  if (-not (Test-Path $Cli)) {
    New-Item -ItemType Directory -Force $Bin | Out-Null
    $Zip = Join-Path $Bin "cli.zip"
    Invoke-WebRequest "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip" -OutFile $Zip
    Expand-Archive $Zip -DestinationPath $Bin -Force
    Remove-Item $Zip
  }
}

# 2. Support ESP32
Write-Host "==> Installation du support ESP32 (long la premiere fois)..."
& $Cli core update-index --additional-urls $Url
& $Cli core install esp32:esp32 --additional-urls $Url

# 3. Port série
if (-not $Port) {
  $Port = (Get-CimInstance Win32_SerialPort | Where-Object { $_.Description -match "CH340|CP210|USB" } | Select-Object -First 1).DeviceID
}
if (-not $Port) {
  & $Cli board list
  Write-Error "ESP32-CAM introuvable. Verifie le cable micro-USB, ou installe le pilote CH340 (wch-ic.com), puis relance avec -Port COMx."
}
Write-Host "==> Port : $Port"

# 4. Compilation + flash
& $Cli compile --fqbn $Fqbn .
Write-Host "==> Flash... (si ca bloque sur 'Connecting...', maintiens IO0 puis appuie sur RST)"
& $Cli upload --fqbn $Fqbn -p $Port .

# 5. Logs de démarrage
Write-Host "==> Demarrage de la camera (Ctrl+C pour quitter) :"
& $Cli monitor -p $Port -c baudrate=115200
