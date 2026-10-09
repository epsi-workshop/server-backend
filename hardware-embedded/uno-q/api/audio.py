"""Enceinte Bluetooth : appairage (bluetoothctl), lecture des sons (PipeWire) et reconnexion automatique.

L'enceinte choisie est mémorisée dans audio.json ; talos s'y reconnecte dès qu'elle est allumée et à portée.
Les sons (bips, carillon, sirène) sont générés au premier démarrage dans sounds/ ; les messages parlés
(voice-*.wav) sont produits sur un Mac avec `say` puis copiés (voir sounds/README).
"""
import json
import math
import os
import pathlib
import re
import struct
import subprocess
import threading
import time
import wave

HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE / "audio.json"
SOUNDS = HERE / "sounds"
RATE = 44100
RECONNECT_S = 20
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
AUDIO_SINK_UUID = "0000110b"  # profil A2DP « Audio Sink » : l'appareil sait jouer du son

ENV = {**os.environ, "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")}
_lock = threading.Lock()  # bluetoothctl : une commande à la fois


class AudioError(Exception):
    pass


def _ctl(*args: str, timeout: float = 15) -> str:
    try:
        r = subprocess.run(["bluetoothctl", *args], capture_output=True, text=True, timeout=timeout, env=ENV)
    except subprocess.TimeoutExpired:
        raise AudioError(f"bluetoothctl {args[-2] if len(args) > 1 else args[0]} : délai dépassé") from None
    return r.stdout + r.stderr


# ---------------------------------------------------------------- configuration
def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {"mac": None, "name": None, "volume": 80}


def save_config(cfg: dict) -> None:
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg))
    os.replace(tmp, CONFIG)


# ---------------------------------------------------------------- Bluetooth
def info(mac: str) -> dict:
    out = _ctl("info", mac, timeout=5)
    name = re.search(r"^\s*Name: (.+)$", out, re.M)
    alias = re.search(r"^\s*Alias: (.+)$", out, re.M)
    icon = re.search(r"^\s*Icon: (.+)$", out, re.M)
    audio = AUDIO_SINK_UUID in out.lower() or bool(icon and icon.group(1).startswith("audio"))
    return {
        "mac": mac,
        "name": (name or alias).group(1).strip() if (name or alias) else None,
        "paired": "Paired: yes" in out,
        "connected": "Connected: yes" in out,
        "audio": audio,
        "rssi": int(m.group(1)) if (m := re.search(r"RSSI: .*?(-?\d+)\)?\s*$", out, re.M)) else None,
    }


def scan(seconds: int = 8) -> list[dict]:
    """Appareils Bluetooth classiques à portée (les enceintes), ceux sans nom sont ignorés."""
    with _lock:
        _ctl("power", "on", timeout=5)
        _ctl("--timeout", str(seconds), "scan", "bredr", timeout=seconds + 5)
        macs = re.findall(r"^Device ((?:[0-9A-F]{2}:){5}[0-9A-F]{2}) ", _ctl("devices", timeout=5), re.M)
        found = [info(m) for m in macs]
    named = [d for d in found if d["name"] and d["name"].replace("-", ":") != d["mac"]]
    # Enceintes d'abord, puis les plus proches
    return sorted(named, key=lambda d: (not d["audio"], not d["connected"], -(d["rssi"] or -999)))


def connect(mac: str | None = None, name: str | None = None) -> dict:
    """Appaire, approuve et connecte l'enceinte (par adresse, ou par nom après une recherche)."""
    if not mac:
        if not name:
            raise AudioError("adresse ou nom de l'enceinte requis")
        wanted = name.strip().lower()
        devices = scan()
        match = next((d for d in devices if d["name"].lower() == wanted), None) or \
            next((d for d in devices if wanted in d["name"].lower()), None)
        if match is None:
            raise AudioError(f"aucune enceinte « {name} » trouvée : est-elle en mode appairage ?")
        mac = match["mac"]
    mac = mac.upper()
    if not MAC_RE.fullmatch(mac):
        raise AudioError("adresse Bluetooth invalide")
    with _lock:
        if not info(mac)["paired"]:
            out = _ctl("--agent", "NoInputNoOutput", "pair", mac, timeout=30)
            if "Failed" in out or "not available" in out:
                raise AudioError("appairage refusé : mettez l'enceinte en mode appairage (voyant qui clignote vite)")
        _ctl("trust", mac, timeout=5)
        out = _ctl("connect", mac, timeout=20)
        dev = info(mac)
    if not dev["connected"]:
        raise AudioError("connexion impossible : " + (out.strip().splitlines() or ["?"])[-1][:120])
    cfg = load_config()
    cfg.update(mac=mac, name=dev["name"])
    save_config(cfg)
    _wait_sink(mac)
    set_volume(cfg.get("volume", 80))
    return status()


def disconnect() -> dict:
    cfg = load_config()
    if cfg.get("mac"):
        with _lock:
            _ctl("disconnect", cfg["mac"], timeout=10)
    return status()


def forget() -> dict:
    """Oublie l'enceinte : plus de reconnexion automatique, appairage supprimé."""
    cfg = load_config()
    if cfg.get("mac"):
        with _lock:
            _ctl("remove", cfg["mac"], timeout=10)
    cfg.update(mac=None, name=None)
    save_config(cfg)
    return status()


# ---------------------------------------------------------------- PipeWire
def _sink_id(mac: str | None) -> int | None:
    """Nœud PipeWire de l'enceinte (Audio/Sink dont api.bluez5.address est son adresse)."""
    if not mac:
        return None
    try:
        nodes = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5, env=ENV).stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return None
    for n in nodes:
        props = (n.get("info") or {}).get("props") or {}
        if props.get("media.class") == "Audio/Sink" and str(props.get("api.bluez5.address", "")).upper() == mac:
            return n["id"]
    return None


def _wait_sink(mac: str, seconds: float = 8) -> int | None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if (sid := _sink_id(mac)) is not None:
            subprocess.run(["wpctl", "set-default", str(sid)], env=ENV, timeout=5)
            return sid
        time.sleep(0.5)
    return None


def set_volume(pct: int) -> dict:
    pct = max(0, min(100, int(pct)))
    cfg = load_config()
    cfg["volume"] = pct
    save_config(cfg)
    if (sid := _sink_id(cfg.get("mac"))) is not None:
        subprocess.run(["wpctl", "set-volume", str(sid), f"{pct / 100:.2f}"], env=ENV, timeout=5)
    return status()


def status() -> dict:
    cfg = load_config()
    dev = info(cfg["mac"]) if cfg.get("mac") else None
    return {
        "speaker": {"mac": cfg["mac"], "name": cfg.get("name"), "connected": bool(dev and dev["connected"])}
        if cfg.get("mac") else None,
        "ready": _sink_id(cfg.get("mac")) is not None,
        "volume": cfg.get("volume", 80),
        "sounds": sorted(p.stem for p in SOUNDS.glob("*.wav")),
    }


# ---------------------------------------------------------------- lecture
# Événements -> sons joués à la suite ; la sirène boucle ensuite pendant `siren` secondes.
EVENTS = {
    "ok": (["ok", "voice-badge-ok"], 0),
    "refused": (["refused", "voice-badge-refused"], 0),
    "hello": (["hello", "voice-bonjour"], 0),
    "intruder": (["voice-intrus"], 10),
    "siren": ([], 10),
    "test": (["test", "voice-test"], 0),
}


class Player:
    """Un événement sonore à la fois ; une sirène en cours n'est interrompue que par stop() ou une autre sirène."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._siren_until = 0.0
        self._lock = threading.Lock()

    def play(self, event: str, siren_seconds: int | None = None) -> bool:
        if event not in EVENTS:
            return False
        sid = _sink_id(load_config().get("mac"))
        if sid is None:
            return False
        sequence, siren = EVENTS[event]
        siren = siren_seconds if siren and siren_seconds else siren
        if not siren and time.monotonic() < self._siren_until:
            return False
        self.stop()
        self._stop = stop = threading.Event()
        if siren:
            self._siren_until = time.monotonic() + siren + 3
        files = [SOUNDS / f"{n}.wav" for n in sequence]
        threading.Thread(target=self._run, args=([f for f in files if f.exists()], sid, siren, stop),
                         daemon=True).start()
        return True

    def _play_file(self, path: pathlib.Path, sid: int) -> None:
        with self._lock:
            self._proc = subprocess.Popen(["pw-play", "--target", str(sid), str(path)], env=ENV,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._proc.wait()

    def _run(self, files: list[pathlib.Path], sid: int, siren: int, stop: threading.Event) -> None:
        for f in files:
            if stop.is_set():
                return
            self._play_file(f, sid)
        end = time.monotonic() + siren
        while siren and not stop.is_set() and time.monotonic() < end:
            self._play_file(SOUNDS / "siren.wav", sid)
        if not stop.is_set():
            self._siren_until = 0.0

    def stop(self) -> None:
        self._stop.set()
        self._siren_until = 0.0
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()


player = Player()


def reconnect_loop() -> None:
    """Reconnexion automatique à l'enceinte mémorisée (allumée après talos, ou revenue à portée)."""
    while True:
        time.sleep(RECONNECT_S)
        mac = load_config().get("mac")
        if not mac or not _lock.acquire(blocking=False):
            continue
        try:
            if not info(mac)["connected"]:
                _ctl("connect", mac, timeout=15)
                if info(mac)["connected"]:
                    _wait_sink(mac)
                    set_volume(load_config().get("volume", 80))
        except AudioError:
            pass
        finally:
            _lock.release()


# ---------------------------------------------------------------- sons générés
def _write(name: str, samples: list[float]) -> None:
    with wave.open(str(SOUNDS / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 30000)) for s in samples))


def _tone(freq: float, ms: int, vol: float = 0.9) -> list[float]:
    n = int(RATE * ms / 1000)
    fade = min(n // 2, int(RATE * 0.008))  # fondu de 8 ms : pas de clic
    return [vol * math.sin(2 * math.pi * freq * i / RATE) * min(1, i / fade if fade else 1, (n - i) / fade if fade else 1)
            for i in range(n)]


def _silence(ms: int) -> list[float]:
    return [0.0] * int(RATE * ms / 1000)


def generate_sounds() -> None:
    """Crée les sons manquants (une fois, au démarrage)."""
    SOUNDS.mkdir(exist_ok=True)
    recipes = {
        "ok": lambda: _tone(1760, 90) + _silence(50) + _tone(2349, 160),
        "refused": lambda: _tone(440, 180) + _silence(60) + _tone(330, 420),
        "hello": lambda: _tone(1047, 140, 0.7) + _tone(1319, 140, 0.7) + _tone(1568, 260, 0.7),
        "test": lambda: sum((_tone(f, 130) for f in (880, 1109, 1319, 1760)), []),
    }
    for name, make in recipes.items():
        if not (SOUNDS / f"{name}.wav").exists():
            _write(name, make())
    if not (SOUNDS / "siren.wav").exists():
        # Sirène deux tons montante/descendante (1 s), avec une harmonique pour qu'elle porte
        n, phase, out = RATE, 0.0, []
        for i in range(n):
            t = i / n
            f = 700 + 900 * (t * 2 if t < 0.5 else 2 - t * 2)
            phase += 2 * math.pi * f / RATE
            out.append(0.75 * math.sin(phase) + 0.2 * math.sin(3 * phase))
        _write("siren", out)
