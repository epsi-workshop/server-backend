#!/usr/bin/env bash
# Sentinel-X : PKI interne (cahier des charges, 8.2).
#
#   scripts/gen-pki.sh            # crée la CA si absente, puis chaque certificat manquant
#   scripts/gen-pki.sh simulator  # ajoute un certificat client (le CN devient l'identifiant MQTT)
#
# Résultat dans pki/ (jamais commité) :
#   ca.key, ca.crt                    autorité de certification ; ca.key ne quitte jamais ce poste
#   broker/  ca.crt broker.crt/.key   Mosquitto 8883 (SAN : 192.168.50.10, sentinel.lan, mosquitto)
#   web/     web.crt/.key             Caddy 443 (SAN : 192.168.50.10, sentinel.lan, ntfy.sentinel.lan)
#   <client>/ ca.crt <client>.crt/.key  un dossier par client MQTT (box01, backend, vision…)
#
# Les extensions (basicConstraints critique, AKID/SKID, keyUsage) sont exigées par la vérification
# stricte de Python 3.13 (VERIFY_X509_STRICT) utilisée par le backend et vision.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKI="$ROOT/pki"
DAYS=365
SERVER_IP="${SERVER_IP:-192.168.50.10}"
if [[ $# -gt 0 ]]; then CLIENTS=("$@"); else CLIENTS=(box01 backend vision anomaly); fi

mkdir -p "$PKI"
chmod 700 "$PKI"
cd "$PKI"
umask 077

if [[ ! -f ca.key ]]; then
  openssl ecparam -name prime256v1 -genkey -noout -out ca.key
  openssl req -x509 -new -key ca.key -sha256 -days "$DAYS" -subj "/CN=Sentinel-X CA" -out ca.crt \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash"
  chmod 644 ca.crt
  echo "CA créée : pki/ca.crt"
fi

# sign <nom> <CN> <extendedKeyUsage> [subjectAltName]
sign() {
  local name="$1" cn="$2" eku="$3" san="${4:-}" dir="$PKI/$1"
  if [[ -f "$dir/$name.crt" ]]; then
    echo "Déjà présent : pki/$name/$name.crt"
    return
  fi
  mkdir -p "$dir"
  openssl ecparam -name prime256v1 -genkey -noout -out "$dir/$name.key"
  openssl req -new -key "$dir/$name.key" -subj "/CN=$cn" -out "$dir/$name.csr"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature,keyAgreement"
    echo "extendedKeyUsage=$eku"
    echo "subjectKeyIdentifier=hash"
    echo "authorityKeyIdentifier=keyid,issuer"
    [[ -n "$san" ]] && echo "subjectAltName=$san"
  } > "$dir/ext.cnf"
  openssl x509 -req -in "$dir/$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -days "$DAYS" -sha256 -extfile "$dir/ext.cnf" -out "$dir/$name.crt" 2>/dev/null
  rm -f "$dir/$name.csr" "$dir/ext.cnf"
  cp ca.crt "$dir/ca.crt"
  chmod 644 "$dir/$name.crt" "$dir/ca.crt"
  chmod 600 "$dir/$name.key"
  echo "Certificat créé : pki/$name/$name.crt (CN=$cn)"
}

sign broker sentinel-server serverAuth \
  "IP:$SERVER_IP,DNS:sentinel.lan,DNS:mosquitto,DNS:localhost,IP:127.0.0.1"
sign web sentinel.lan serverAuth \
  "IP:$SERVER_IP,DNS:sentinel.lan,DNS:ntfy.sentinel.lan,DNS:localhost,IP:127.0.0.1"
for c in "${CLIENTS[@]}"; do
  sign "$c" "$c" clientAuth
done

echo
echo "Étape suivante : scripts/fix-owners.sh (propriétaires attendus par chaque conteneur)."
