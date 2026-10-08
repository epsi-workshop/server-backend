"""Superviseur Sentinel-X : état des services et redémarrages demandés par le backend (liste fermée).

C'est le seul conteneur qui accède au socket Docker, ce qui équivaut à être root sur l'hôte. D'où :
- liste blanche figée des services redémarrables (RESTARTABLE) ; de l'API Docker, seules la liste et l'état des
  conteneurs du projet (lecture) et POST /containers/<id>/restart sont utilisés ;
- joignable uniquement depuis le réseau interne « supervision » (backend seul), jeton partagé obligatoire ;
- utilisateur non-root dans le groupe docker de l'hôte, système de fichiers en lecture seule, aucune capacité.

Routes : GET /services (état des conteneurs du projet), POST /restart/<service> (202, redémarrage en arrière-plan).
Bibliothèque standard uniquement : pas de dépendance à auditer.
"""
import hmac
import http.client
import json
import logging
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote

PROJECT = os.environ.get("COMPOSE_PROJECT", "sentinel-x")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
DOCKER_SOCKET = "/var/run/docker.sock"
RESTARTABLE = ("vision", "anomaly", "mosquitto", "backend")
PORT = 8090

log = logging.getLogger("supervisor")


class DockerConnection(http.client.HTTPConnection):
    """API Docker sur le socket Unix."""

    def __init__(self, timeout: float = 30) -> None:
        super().__init__("localhost", timeout=timeout)

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(DOCKER_SOCKET)
        self.sock = s


def docker(method: str, path: str, timeout: float = 30) -> tuple[int, Any]:
    conn = DockerConnection(timeout)
    try:
        conn.request(method, path)
        r = conn.getresponse()
        body = r.read()
        return r.status, json.loads(body) if body else None
    finally:
        conn.close()


def project_containers() -> dict[str, dict[str, Any]]:
    """Conteneurs du projet compose, par nom de service."""
    filters = json.dumps({"label": [f"com.docker.compose.project={PROJECT}"]})
    status, data = docker("GET", "/containers/json?all=1&filters=" + quote(filters))
    if status != 200:
        raise RuntimeError(f"API Docker : {status}")
    return {c["Labels"]["com.docker.compose.service"]: c for c in data
            if "com.docker.compose.service" in c.get("Labels", {})}


def cpu_percent(stats: dict[str, Any]) -> float:
    """Part du CPU de l'hôte, calculée comme `docker stats`."""
    cpu, pre = stats.get("cpu_stats", {}), stats.get("precpu_stats", {})
    delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
    system = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    cpus = cpu.get("online_cpus") or 1
    return round(delta / system * cpus * 100, 1) if delta > 0 and system > 0 else 0.0


def health_status(state: dict[str, Any]) -> str:
    """ok, degrade (en démarrage, malade, redémarrage) ou arrete."""
    if not state.get("Running"):
        return "arrete"
    health = (state.get("Health") or {}).get("Status")
    return "degrade" if state.get("Restarting") or health in ("unhealthy", "starting") else "ok"


def uptime_s(state: dict[str, Any], now: datetime) -> int:
    started = state.get("StartedAt") or ""
    if not state.get("Running") or not started or started.startswith("0001"):
        return 0
    start = datetime.fromisoformat(started[:26].rstrip("Z") + "+00:00" if "." in started else started.replace("Z", "+00:00"))
    return max(0, int((now - start).total_seconds()))


def version_of(image: str) -> str:
    """Étiquette de l'image, sans le « v » de certaines (le dashboard l'ajoute) : ntfy:v2.28.0 -> 2.28.0."""
    return image.rsplit(":", 1)[1].removeprefix("v") if ":" in image.rsplit("/", 1)[-1] else "latest"


def describe(service: str, container: dict[str, Any]) -> dict[str, Any]:
    _, info = docker("GET", f"/containers/{container['Id']}/json")
    _, stats = docker("GET", f"/containers/{container['Id']}/stats?stream=false", timeout=10)
    state = info["State"]
    mem = (stats or {}).get("memory_stats", {}).get("usage", 0) if state.get("Running") else 0
    return {
        "name": service, "restartable": service in RESTARTABLE, "status": health_status(state),
        "uptime_s": uptime_s(state, datetime.now(UTC)), "cpu": cpu_percent(stats or {}) if state.get("Running") else 0.0,
        "mem_mb": round(mem / 2**20, 1), "version": version_of(info["Config"]["Image"]),
    }


def services() -> list[dict[str, Any]]:
    containers = {s: c for s, c in project_containers().items() if c.get("State") != "exited" or s in RESTARTABLE}
    with ThreadPoolExecutor(max_workers=8) as pool:  # stats prend environ 1 s par conteneur
        return sorted(pool.map(lambda kv: describe(*kv), containers.items()), key=lambda s: s["name"])


def restart(service: str) -> None:
    container = project_containers().get(service)
    if container is None:
        log.error("Redémarrage de %s impossible : conteneur introuvable", service)
        return
    status, _ = docker("POST", f"/containers/{container['Id']}/restart?t=10", timeout=60)
    log.log(logging.INFO if status == 204 else logging.ERROR, "Redémarrage de %s : %s", service, status)


def authorized(header: str | None) -> bool:
    if not TOKEN or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header.removeprefix("Bearer ").encode(), TOKEN.encode())


class Handler(BaseHTTPRequestHandler):
    server_version = "sentinel-supervisor"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s %s", self.address_string(), fmt % args)

    def _reply(self, code: int, body: Any = None) -> None:
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not authorized(self.headers.get("Authorization")):
            return self._reply(401, {"detail": "jeton invalide"})
        if self.path != "/services":
            return self._reply(404, {"detail": "route inconnue"})
        try:
            self._reply(200, services())
        except (OSError, RuntimeError) as e:
            log.error("État des services indisponible : %s", e)
            self._reply(502, {"detail": "API Docker injoignable"})

    def do_POST(self) -> None:
        if not authorized(self.headers.get("Authorization")):
            return self._reply(401, {"detail": "jeton invalide"})
        service = self.path.removeprefix("/restart/")
        if not self.path.startswith("/restart/") or service not in RESTARTABLE:
            return self._reply(403, {"detail": "service hors liste blanche"})
        # Réponse immédiate : le backend peut se redémarrer lui-même sans couper sa propre requête.
        threading.Thread(target=restart, args=(service,), daemon=True).start()
        self._reply(202, {"service": service})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    if not TOKEN:
        log.error("SUPERVISOR_TOKEN vide : toutes les requêtes seront refusées")
    log.info("Superviseur du projet %s sur le port %d, redémarrables : %s", PROJECT, PORT, ", ".join(RESTARTABLE))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
