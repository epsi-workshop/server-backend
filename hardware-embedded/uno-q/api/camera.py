"""Relais du flux MJPEG de l'ESP32-CAM.

Une seule connexion est ouverte vers la caméra (elle ne sert qu'un client
à la fois) ; les images sont redistribuées à tous les spectateurs.
La connexion amont n'est active que tant qu'au moins un client regarde.
"""
import asyncio
import contextlib
import os
import re
import time

import httpx

# Adresses essayées dans l'ordre : client d'un Wi-Fi (mDNS) puis point d'accès de la caméra
CAM_HOSTS = os.environ.get("ESP32CAM_HOST", "esp32cam.local,192.168.4.1").split(",")
BOUNDARY = b"frame"
_LEN_RE = re.compile(rb"Content-Length:\s*(\d+)", re.I)


class CameraHub:
    def __init__(self):
        self.host: str | None = None
        self.frame: bytes | None = None
        self.frame_ts = 0.0
        self.frame_id = 0
        self.viewers = 0
        self.error: str | None = None
        self.mode: str | None = None  # "stream" (port 81) ou "capture" (photos en boucle)
        self._cond = asyncio.Condition()
        self._task: asyncio.Task | None = None

    async def _find_host(self) -> str:
        """Renvoie la première adresse où la caméra répond."""
        candidates = [self.host] + CAM_HOSTS if self.host else CAM_HOSTS
        async with httpx.AsyncClient(timeout=2) as client:
            for host in dict.fromkeys(candidates):
                with contextlib.suppress(Exception):
                    (await client.get(f"http://{host}/status")).raise_for_status()
                    self.host = host
                    return host
        raise ConnectionError("camera introuvable sur " + ", ".join(CAM_HOSTS))

    async def _run(self):
        while self.viewers > 0:
            try:
                host = await self._find_host()
                try:
                    await self._run_stream(host)
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                    # Port 81 indisponible ou muet : on reconstitue le flux avec /capture en boucle
                    await self._run_capture(host)
            except Exception as e:  # caméra injoignable, coupure Wi-Fi...
                self.error = f"{type(e).__name__}: {e}"
                await asyncio.sleep(2)

    async def _run_capture(self, host: str):
        self.mode = "capture"
        async with httpx.AsyncClient(timeout=5) as client:
            while self.viewers > 0:
                r = await client.get(f"http://{host}/capture")
                r.raise_for_status()
                self.error = None
                await self._publish(r.content)

    async def _run_stream(self, host: str):
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3, read=3)) as client:
            async with client.stream("GET", f"http://{host}:81/stream") as resp:
                resp.raise_for_status()
                self.error = None
                self.mode = "stream"
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    while True:
                        head_end = buf.find(b"\r\n\r\n")
                        if head_end < 0:
                            break
                        m = _LEN_RE.search(buf[:head_end])
                        if not m:
                            buf = buf[head_end + 4:]
                            continue
                        size = int(m.group(1))
                        start = head_end + 4
                        if len(buf) < start + size:
                            break
                        await self._publish(buf[start:start + size])
                        buf = buf[start + size:]
                    if self.viewers <= 0:
                        return

    async def _publish(self, jpeg: bytes):
        async with self._cond:
            self.frame, self.frame_ts = jpeg, time.time()
            self.frame_id += 1
            self._cond.notify_all()

    def _ensure_running(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def frames(self):
        """Générateur multipart/x-mixed-replace pour un spectateur."""
        self.viewers += 1
        self._ensure_running()
        last_id = self.frame_id  # on attend une image reçue après la connexion
        try:
            while True:
                async with self._cond:
                    await self._cond.wait_for(lambda: self.frame_id != last_id and self.frame is not None)
                    jpeg, last_id = self.frame, self.frame_id
                yield (b"--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
        finally:
            self.viewers -= 1

    async def snapshot(self) -> bytes:
        # Si un flux tourne, on renvoie la dernière image (la caméra est occupée)
        if self.viewers > 0 and self.frame and time.time() - self.frame_ts < 2:
            return self.frame
        host = await self._find_host()
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"http://{host}/capture")
            r.raise_for_status()
            return r.content

    async def status(self):
        info = {"host": self.host, "mode": self.mode, "candidates": CAM_HOSTS, "viewers": self.viewers, "last_error": self.error,
                "last_frame_age_s": round(time.time() - self.frame_ts, 1) if self.frame else None}
        with contextlib.suppress(Exception):
            host = await self._find_host()
            info["host"] = host
            async with httpx.AsyncClient(timeout=3) as client:
                info["camera"] = (await client.get(f"http://{host}/status")).json()
        info.setdefault("camera", None)
        return info

    async def stop(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


camera_hub = CameraHub()
