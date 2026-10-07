#!/usr/bin/env bash
# Modèles de reconnaissance faciale (OpenCV Zoo, licence Apache 2.0 / MIT) dans models/ :
#   YuNet (détection, 0,2 Mo) et SFace (empreinte du visage, 37 Mo). Utilisés par le backend et le service vision.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models
BASE=https://github.com/opencv/opencv_zoo/raw/main/models
fetch() {  # fichier, url, sha256
  if [ -f "models/$1" ] && echo "$3  models/$1" | shasum -a 256 -c --status; then echo "ok   $1"; return; fi
  curl -fsSL -o "models/$1.part" "$2"
  echo "$3  models/$1.part" | shasum -a 256 -c --status || { echo "somme de contrôle invalide : $1" >&2; rm -f "models/$1.part"; exit 1; }
  mv "models/$1.part" "models/$1"
  echo "téléchargé $1"
}
fetch face_detection_yunet_2023mar.onnx "$BASE/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
fetch face_recognition_sface_2021dec.onnx "$BASE/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
  0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79
