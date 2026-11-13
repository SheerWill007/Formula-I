"""
Embedding adapter (Task 8).

Produces fixed-dimension vectors for strategy-document text. Uses an
OpenAI-compatible ``/embeddings`` endpoint when an API key is configured, and a
deterministic local hash embedding otherwise (development/tests). The dimension
is always ``settings.embedding_dimensions`` so it matches the Vectorize index.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request

from backend.config import settings
from backend.net import safe_urlopen


class EmbeddingError(Exception):
    """Raised when an embedding cannot be produced."""


def embedding_dimensions() -> int:
    dims = int(settings.embedding_dimensions)
    if dims <= 0:
        raise EmbeddingError("embedding_dimensions must be positive")
    return dims


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _local_embedding(text: str, dims: int) -> list[float]:
    """Deterministic, dependency-free embedding (normalised bag of hashes)."""
    vector = [0.0] * dims
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def _provider_embeddings(texts: list[str]) -> list[list[float]]:
    payload = json.dumps({"model": settings.embedding_model, "input": texts}).encode(
        "utf-8"
    )
    request = urllib.request.Request(
        f"{settings.embedding_base_url.rstrip('/')}/embeddings",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.embedding_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with safe_urlopen(
            request, timeout=settings.embedding_timeout_seconds
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EmbeddingError(f"embedding HTTP {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise EmbeddingError(f"embedding call failed: {exc}") from exc

    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingError("embedding provider returned no vectors")

    vectors: list[list[float]] = []
    for item in sorted(data, key=lambda d: d.get("index", 0)):
        vector = item.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError("embedding provider returned a malformed vector")
        vectors.append([float(v) for v in vector])
    return vectors


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    dims = embedding_dimensions()
    if settings.embedding_api_key:
        vectors = _provider_embeddings(texts)
        mismatch = [i for i, v in enumerate(vectors) if len(v) != dims]
        if mismatch:
            raise EmbeddingError(
                f"embedding dimension mismatch: provider returned non-{dims}-dim vectors"
            )
        return vectors
    return [_local_embedding(text, dims) for text in texts]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
