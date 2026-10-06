"""Serveur MJPEG du flux annoté. Plusieurs clients possibles (backend, sonde) : l'image est partagée."""
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

FRAME_TIMEOUT_S = 5  # sans nouvelle image, on ferme : le client verra que la caméra ne répond plus


class FrameHub:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._id = 0

    def publish(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._id += 1
            self._cond.notify_all()

    def next(self, last_id: int, timeout: float) -> tuple[int, bytes | None]:
        """Image suivante (plus récente que last_id), ou None si aucune n'arrive à temps."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._id != last_id, timeout):
                return last_id, None
            return self._id, self._jpeg


def serve(hub: FrameHub, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (nom imposé par http.server)
            if self.path != "/stream":
                self.send_error(404)
                return
            fid, jpeg = hub.next(0, FRAME_TIMEOUT_S)
            if jpeg is None:
                self.send_error(503, "Aucune image de la caméra")
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while jpeg is not None:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                    fid, jpeg = hub.next(fid, FRAME_TIMEOUT_S)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # client parti

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # pas une ligne de journal par connexion

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="mjpeg", daemon=True).start()
    log.info("Flux annoté sur http://%s:%d/stream", host, port)
    return server
