import io

from backend.api.v1 import driver_images
from backend.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100


class FakeR2:
    def __init__(self, objects):
        self.objects = objects
        self.keys = []

    def get_object(self, Bucket, Key):
        self.keys.append(Key)
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}


def _use(monkeypatch, objects):
    fake = FakeR2(objects)
    monkeypatch.setattr(driver_images, "_r2_client", lambda: fake)
    monkeypatch.setattr(settings, "r2_endpoint_url", "https://example.r2")
    return fake


def test_photo_is_public_and_cacheable(app, monkeypatch):
    fake = _use(monkeypatch, {"drivers/ver.png": PNG})
    resp = app.test_client().get("/api/v1/drivers/VER/image")  # no token
    assert resp.status_code == 200
    assert resp.mimetype == "image/png" and resp.data == PNG
    assert "s-maxage" in resp.headers["Cache-Control"]
    assert fake.keys == ["drivers/ver.png"]


def test_unknown_driver_is_404(app, monkeypatch):
    _use(monkeypatch, {})
    assert app.test_client().get("/api/v1/drivers/zzz/image").status_code == 404


def test_etag_gives_304(app, monkeypatch):
    _use(monkeypatch, {"drivers/ver.png": PNG})
    c = app.test_client()
    etag = c.get("/api/v1/drivers/ver/image").headers["ETag"]
    again = c.get("/api/v1/drivers/ver/image", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_bad_codes_never_reach_r2(app, monkeypatch):
    fake = _use(monkeypatch, {})
    c = app.test_client()
    for code in ("a", "toolong", "ve1", "..%2Fsecret"):
        assert c.get(f"/api/v1/drivers/{code}/image").status_code in (401, 404)
    assert fake.keys == []


def test_the_profile_route_is_public(app):
    assert app.test_client().get("/api/v1/drivers/ver/profile").status_code != 401


def test_no_r2_configured_is_404_not_500(app, monkeypatch):
    monkeypatch.setattr(settings, "r2_endpoint_url", "")
    assert app.test_client().get("/api/v1/drivers/ver/image").status_code == 404
