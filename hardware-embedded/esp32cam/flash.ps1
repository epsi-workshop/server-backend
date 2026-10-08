# Flash de l'ESP32-CAM (Windows).
# Usage : clic droit > "Exécuter avec PowerShell"
#    ou : powershell -ExecutionPolicy Bypass -File flash.ps1 [-Port COM5]
param([string]$Port = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Url  = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
# DIO / 40 MHz : plus tolérant que QIO / 80 MHz sur les puces flash des clones ESP32-CAM
$Fqbn = "esp32:esp32:esp32cam:FlashMode=dio,FlashFreq=40"
# 115200 bauds : le 460800 par défaut est instable sur les cartes ESP32-CAM-MB
$Speed = "115200"
$Bin  = Join-Path $PSScriptRoot ".tools"

if (-not (Test-Path secrets.h)) {
  Copy-Item secrets.example.h secrets.h
  Write-Error "secrets.h cree : renseigne le nom et le mot de passe du Wi-Fi, puis relance ce script."
}
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

# 4. Compilation + flash (3 tentatives)
& $Cli compile --fqbn $Fqbn .
if ($LASTEXITCODE -ne 0) { Write-Error "Echec de la compilation." }

$ok = $false
for ($try = 1; $try -le 3 -and -not $ok; $try++) {
  Write-Host "==> Flash, tentative $try/3 (si ca bloque sur 'Connecting...', maintiens IO0 puis appuie sur RST)"
  & $Cli upload --fqbn $Fqbn -p $Port --upload-property "upload.speed=$Speed" .
  $ok = ($LASTEXITCODE -eq 0)
  if (-not $ok -and $try -lt 3) {
    Write-Host "Echec. Maintiens IO0, appuie sur RST, relache IO0, puis appuie sur Entree pour reessayer." -ForegroundColor Yellow
    Read-Host | Out-Null
  }
}
if (-not $ok) {
  Write-Error "Le flash a echoue 3 fois. Essaie un autre cable micro-USB ou un autre port USB (de preference directement sur le PC, sans hub)."
}

# 5. Logs de démarrage
# DTR/RTS désactivés : sur l'ESP32-CAM-MB ils maintiendraient la carte en reset
Write-Host "==> Flash reussi. Appuie sur RST pour voir le demarrage (Ctrl+C pour quitter) :" -ForegroundColor Green
& $Cli monitor -p $Port -c baudrate=115200,dtr=off,rts=off
