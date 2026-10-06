import asyncio

from app import camera as camera_module
from app.camera import CameraRelay, split_jpegs

A = b"\xff\xd8image-A\xff\xd9"
B = b"\xff\xd8image-B\xff\xd9"


def test_split_complete_frames_with_multipart_headers() -> None:
    buf = b"--123\r\nContent-Type: image/jpeg\r\n\r\n" + A + b"\r\n--123\r\n\r\n" + B + b"\r\n--1"
    frames, rest = split_jpegs(buf)
    assert frames == [A, B]
    assert rest == b"1"


def test_split_keeps_incomplete_frame() -> None:
    frames, rest = split_jpegs(b"junk" + A[:5])
    assert frames == []
    assert rest == A[:5]
    frames, rest = split_jpegs(rest + A[5:])
    assert frames == [A]


def test_split_soi_cut_between_two_chunks() -> None:
    frames, rest = split_jpegs(b"entete\xff")
    assert (frames, rest) == ([], b"\xff")
    frames, _ = split_jpegs(rest + A[1:])
    assert frames == [A]


def test_relay_reads_fake_camera(monkeypatch) -> None:
    """Fausse ESP32-CAM : réponse multipart envoyée en petits morceaux, coupés au milieu des images."""
    async def scenario() -> list[bytes]:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=123\r\n\r\n")
            body = b"".join(b"--123\r\nContent-Type: image/jpeg\r\n\r\n" + f + b"\r\n" for f in (A, B, A))
            for i in range(0, len(body), 7):
                writer.write(body[i:i + 7])
                await writer.drain()
                await asyncio.sleep(0.001)
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(camera_module.config, "camera_url", f"http://127.0.0.1:{port}/stream")
        relay = CameraRelay()
        got = [f async for f in relay.frames()]
        server.close()
        return got

    assert asyncio.run(scenario()) == [A, B, A]
