"""Outbound HTTP guard: https only, allow-listed hosts, no redirects."""

import urllib.request
from urllib.parse import urlparse

from backend.config import settings


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def safe_urlopen(request: urllib.request.Request, timeout: float):
    url = urlparse(request.full_url)
    allowed = {
        h.strip() for h in settings.outbound_allowed_hosts.split(",") if h.strip()
    }
    if url.scheme != "https" or url.hostname not in allowed:
        raise ValueError(f"blocked outbound request to {url.hostname!r}")
    return _opener.open(request, timeout=timeout)
