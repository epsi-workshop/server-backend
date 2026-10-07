import base64
import json

import cv2
import numpy as np
import pytest
from fastapi import HTTPException

from app import faces
from app.config import config
from app.routers.admin import _decode_photo


def test_decode_photo_accepts_data_url():
    raw = b"\xff\xd8jpeg"
    assert _decode_photo("data:image/jpeg;base64," + base64.b64encode(raw).decode()) == raw


def test_decode_photo_rejects_garbage():
    with pytest.raises(HTTPException):
        _decode_photo("pas du base64 !")


def test_enroll_rejects_unreadable_image():
    with pytest.raises(faces.EnrollError, match="illisible"):
        faces.enroll(b"pas une image")


@pytest.mark.skipif(not (config.face_models_dir / faces.DETECTOR_MODEL).exists(), reason="modèles non téléchargés")
def test_enroll_rejects_photo_without_face():
    blank = cv2.imencode(".jpg", np.full((480, 640, 3), 128, np.uint8))[1].tobytes()
    with pytest.raises(faces.EnrollError, match="Aucun visage"):
        faces.enroll(blank)


def test_write_gallery_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "faces_dir", tmp_path)
    faces.write_gallery([{"id": "a", "name": "Léa", "embedding": [0.1] * 128}])
    data = json.loads((tmp_path / "gallery.json").read_text(encoding="utf-8"))
    assert data["members"][0]["name"] == "Léa"
    assert not list(tmp_path.glob("*.tmp"))
