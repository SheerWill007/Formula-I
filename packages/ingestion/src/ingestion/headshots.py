"""Driver headshot URLs on F1's media CDN.

The drivers table has a headshot_url column, but ingestion never filled it, so
the driver page had nothing to show on the deployed site. F1's CDN serves
every driver at a predictable URL, and answers 200 with a generic placeholder
for names it does not know, so a guess is only accepted when the image differs
from that placeholder.

    python -m ingestion.headshots            # dry run: show what would be set
    python -m ingestion.headshots --apply    # fill drivers.headshot_url where empty
"""

from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator

import structlog
from sqlalchemy import create_engine, text

from ingestion.config import settings

log = structlog.get_logger()

_BASE = "https://media.formula1.com/d_driver_fallback_image.png/content/dam/fom-website/drivers"
# 4col is a 432px square: sharp enough for the profile circle, about 55 KB.
_SIZE = "4col"

# F1 files a few drivers under a longer first name than the timing feed uses.
_FULL_NAMES = {"ANT": "Andrea Kimi Antonelli"}

Fetch = Callable[[str], bytes | None]


def _ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )


def _url(first: str, last: str) -> str:
    first_a, last_a = _ascii(first), _ascii(last)
    code = f"{first_a.split()[0][:3]}{last_a.split()[0][:3]}01"
    folder = f"{code.upper()}_{first_a}_{last_a}"
    return (
        f"{_BASE}/{first_a[0].upper()}/{urllib.parse.quote(folder)}/"
        f"{code.lower()}.png.transform/{_SIZE}/image.png"
    )


def candidates(full_name: str, abbreviation: str | None = None) -> Iterator[str]:
    """URLs to try, most likely first. Western order, then family-name-first."""
    name = _FULL_NAMES.get((abbreviation or "").upper(), full_name).strip()
    parts = [p for p in re.split(r"\s+", name) if p]
    if len(parts) < 2:
        return
    yield _url(" ".join(parts[:-1]), parts[-1])
    if len(parts) > 2:
        yield _url(parts[0], parts[-1])
    yield _url(parts[-1], " ".join(parts[:-1]))  # e.g. "Zhou Guanyu"


def upsize(url: str | None) -> str | None:
    """FastF1 and OpenF1 hand out the 93px thumbnail; use the sharper size."""
    if not url:
        return None
    return url.replace(".transform/1col/", f".transform/{_SIZE}/")


def _fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.read()
    except Exception:
        return None


def _placeholder_digest(fetch: Fetch) -> str | None:
    body = fetch(_url("Not", "Realdriver"))
    return hashlib.md5(body).hexdigest() if body else None


def resolve(
    full_name: str,
    abbreviation: str | None = None,
    *,
    fetch: Fetch = _fetch,
    placeholder: str | None = None,
) -> str | None:
    """The first candidate URL that serves a real image, not the CDN placeholder."""
    placeholder = placeholder or _placeholder_digest(fetch)
    for url in candidates(full_name, abbreviation):
        body = fetch(url)
        if not body or len(body) < 1500:
            continue
        if placeholder and hashlib.md5(body).hexdigest() == placeholder:
            continue
        return url
    return None


def backfill(*, apply: bool, fetch: Fetch = _fetch) -> dict[str, str | None]:
    """Set headshot_url on every driver row that has none. Returns code -> url."""
    engine = create_engine(settings.db_url)
    found: dict[str, str | None] = {}
    placeholder = _placeholder_digest(fetch)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ON (abbreviation) abbreviation, full_name
                FROM drivers
                WHERE headshot_url IS NULL AND full_name IS NOT NULL
                ORDER BY abbreviation, session_key DESC
                """
            )
        ).all()
        for abbreviation, full_name in rows:
            url = resolve(full_name, abbreviation, fetch=fetch, placeholder=placeholder)
            found[abbreviation] = url
            if url and apply:
                conn.execute(
                    text(
                        "UPDATE drivers SET headshot_url = :u "
                        "WHERE abbreviation = :a AND headshot_url IS NULL"
                    ),
                    {"u": url, "a": abbreviation},
                )
    engine.dispose()
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill drivers.headshot_url from F1's CDN")
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args(argv)
    found = backfill(apply=args.apply)
    hits = {k: v for k, v in found.items() if v}
    misses = sorted(k for k, v in found.items() if not v)
    mode = "updated" if args.apply else "would update"
    print(f"{mode} {len(hits)} driver(s); no image found for: {misses or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
