"""Client minimal du Bridge UNO Q (msgpack-rpc via arduino-router)."""
import math
import socket
import threading

import msgpack

SOCKET_PATH = "/run/arduino-router.sock"
_lock = threading.Lock()
_msgid = 0


class BridgeError(Exception):
    pass


def call(method, *params, timeout=3.0):
    global _msgid
    with _lock:
        _msgid = (_msgid + 1) % 2**31
        msgid = _msgid
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(SOCKET_PATH)
            s.sendall(msgpack.packb([0, msgid, method, list(params)]))
            unpacker = msgpack.Unpacker(raw=False)
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    raise BridgeError("connection closed by router")
                unpacker.feed(chunk)
                for msg in unpacker:
                    if msg[0] == 1 and msg[1] == msgid:
                        if msg[2]:
                            raise BridgeError(str(msg[2]))
                        return msg[3]


def read_float(method):
    """Appelle une méthode du MCU ; None si NaN ou erreur."""
    try:
        v = call(method)
    except (BridgeError, OSError):
        return None
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(v, 1)


def read_int(method):
    """Appelle une méthode entière du MCU ; None si erreur."""
    try:
        return call(method)
    except (BridgeError, OSError):
        return None
