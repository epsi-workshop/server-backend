# Sentinel-X : ouvre Mosquitto au Wi-Fi pour le boîtier (port 1884, identifiant box01, ACL).
# À exécuter en administrateur. Le port 1883 reste limité à ce PC (backend, vision).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$logFile = Join-Path $here "setup-mosquitto-lan.log"
Start-Transcript -Path $logFile -Force | Out-Null

$mq = "C:\Program Files\mosquitto"
$conf = Join-Path $mq "mosquitto.conf"
$backup = Join-Path $mq "mosquitto.conf.avant-sentinel"
$data = "C:\ProgramData\sentinel-x\mosquitto"   # chemins sans espace pour mosquitto.conf
$marker = "# --- Sentinel-X ---"

try {
    New-Item -ItemType Directory -Force $data | Out-Null
    if (-not (Test-Path $backup)) { Copy-Item $conf $backup; "Sauvegarde : $backup" }

    # Compte du boîtier (mot de passe haché par mosquitto_passwd)
    # Même mot de passe que la passerelle (firmware/gateway/gateway.env, jamais commité).
    $gwEnv = Join-Path $here "..\firmware\gateway\gateway.env"
    $line = Get-Content $gwEnv | Where-Object { $_ -match '^MQTT_PASSWORD=.+' } | Select-Object -First 1
    if (-not $line) { throw "MQTT_PASSWORD absent de $gwEnv" }
    $pwd = ($line -replace '^MQTT_PASSWORD=', '').Trim()
    & (Join-Path $mq "mosquitto_passwd.exe") -c -b (Join-Path $data "passwd") box01 $pwd
    if ($LASTEXITCODE -ne 0) { throw "mosquitto_passwd a échoué" }
    # mosquitto_passwd réserve le fichier au compte qui l'a créé ; le service tourne sous SYSTEM
    # (SID S-1-5-18, indépendant de la langue de Windows) : lecture seule pour lui, sinon il ne démarre pas.
    & icacls (Join-Path $data "passwd") /grant "*S-1-5-18:R" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls a échoué sur le fichier passwd" }

    # Droits du boîtier : il n'écrit que sur ses topics et ne lit que ses commandes (cahier des charges).
    @"
user box01
topic write sentinel/box01/telemetry
topic write sentinel/box01/event
topic write sentinel/box01/heartbeat
topic write sentinel/box01/status
topic read sentinel/box01/cmd
"@ | Set-Content -Encoding ascii (Join-Path $data "acl")

    $block = @"

$marker
log_dest file C:/ProgramData/sentinel-x/mosquitto/mosquitto.log
per_listener_settings true

# Backend et vision, sur ce PC uniquement (developpement, sans authentification).
listener 1883 127.0.0.1
allow_anonymous true

# Boitier, sur le Wi-Fi : identifiant + mot de passe, droits limites (TLS a venir : #11, #12).
listener 1884
allow_anonymous false
password_file C:/ProgramData/sentinel-x/mosquitto/passwd
acl_file C:/ProgramData/sentinel-x/mosquitto/acl
"@
    $current = Get-Content $conf -Raw
    if ($current -notmatch [regex]::Escape($marker)) {
        Add-Content -Encoding ascii $conf $block
        "Configuration ajoutée à $conf"
    } else { "Configuration Sentinel-X déjà présente" }

    # Arrêt complet et ports libérés avant de redémarrer (le backend et vision étaient connectés au 1883).
    Stop-Service mosquitto -Force
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort 1883, 1884 -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    Start-Service mosquitto
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if ((Get-Service mosquitto).Status -eq "Running" -and
            (Get-NetTCPConnection -State Listen -LocalPort 1884 -ErrorAction SilentlyContinue)) { $ok = $true; break }
    }
    if (-not $ok) {
        "Le service ne démarre pas. Diagnostic (Mosquitto lancé à la main avec la même configuration) :"
        Stop-Service mosquitto -Force -ErrorAction SilentlyContinue
        $p = Start-Process -FilePath (Join-Path $mq "mosquitto.exe") -ArgumentList "-v", "-c", "`"$conf`"" `
            -RedirectStandardError (Join-Path $here "mosquitto-diag.log") -NoNewWindow -PassThru
        Start-Sleep -Seconds 3
        if (-not $p.HasExited) { $p.Kill(); "(démarrage manuel réussi : le problème est propre au service)" }
        Get-Content (Join-Path $here "mosquitto-diag.log")
        Copy-Item $backup $conf -Force
        Start-Service mosquitto
        throw "Configuration d'origine restaurée, Mosquitto relancé comme avant"
    }
    "Mosquitto redémarré, ports 1883 (local) et 1884 (Wi-Fi) ouverts"

    $rule = "Sentinel-X MQTT boitier (1884)"
    if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort 1884 `
            -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
        "Pare-feu : port 1884 ouvert au réseau local uniquement"
    } else { "Règle de pare-feu déjà présente" }

    Get-NetTCPConnection -State Listen -LocalPort 1883, 1884 | ForEach-Object { "Écoute : $($_.LocalAddress):$($_.LocalPort)" }
    "TERMINE"
} catch {
    "ERREUR : $_"
} finally {
    Stop-Transcript | Out-Null
}
