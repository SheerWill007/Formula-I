"""Public driver photos, served from the private R2 bucket.

The cutout PNGs are not in the repo (they are gitignored on purpose), so the
deployed site cannot serve them as static files. They live in R2 under
drivers/<code>.png and the frontend rewrites /drivers/<code>.png here. The
bucket stays private (it also holds telemetry); only these images are exposed.
There is no login on this route because <img> tags cannot send a token.
"""

from __future__ import annotations

import hashlib
import re

from flask import Blueprint, Response, request

from backend.api.v1.telemetry import _r2_client
from backend.config import settings

driver_images_bp = Blueprint("driver_images", __name__)

_CODE = re.compile(r"[a-z]{2,4}")
_CACHE = "public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400"


def _not_found():
    return Response("Not found", status=404, mimetype="text/plain")


@driver_images_bp.get("/drivers/<code>/image")
def driver_image(code: str):
    code = code.strip().lower()
    if not _CODE.fullmatch(code) or not settings.r2_endpoint_url:
        return _not_found()
    try:
        obj = _r2_client().get_object(
            Bucket=settings.telemetry_artifact_bucket, Key=f"drivers/{code}.png"
        )
        body = obj["Body"].read()
    except Exception:
        return _not_found()  # no such photo, or R2 unreachable: the page falls back

    etag = hashlib.md5(body).hexdigest()
    if request.headers.get("If-None-Match") == f'"{etag}"':
        return Response(status=304, headers={"ETag": f'"{etag}"', "Cache-Control": _CACHE})
    return Response(
        body,
        mimetype="image/png",
        headers={"ETag": f'"{etag}"', "Cache-Control": _CACHE},
    )
