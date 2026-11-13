"""Semantic cache for F1 agent queries.

Before hitting the LLM router, check if a nearly identical question was already answered. Saves API cost + latency.

How it works:
  1. Normalize the query (lowercase, strip whitespace)
  2. Convert to a vector of character n-gram frequencies
  3. Compute cosine similarity against stored queries
  4. If similarity > THRESHOLD -> return cached response
  5. Otherwise -> proceed to LLM, then store result
"""

from __future__ import annotations
import math
import time
import structlog
from dataclasses import dataclass, field

log = structlog.get_logger()

SIMILARITY_THRESHOLD = 0.95
CACHE_TTL_SECONDS = 3600
NGRAM_SIZE = 3


@dataclass(frozen=True)
class CacheEntry:
    """A single cached query response pair"""

    query: str
    response: dict
    normalized_query: str
    ngram_vector: dict[str, int]
    created_at: float


@dataclass
class SemanticCache:
    """In memory semantic cache with cosine similarity on character n-grams

    Usage:
        cache = SemanticCache()

        #check the cache before the llm call
        cached = cache.get(user_query)
        if cached is not None:
            return cache # cache hit

        #cache miss
        result = call_llm(user_query)

        #store resul
        cache.set(user_query, result)
    """

    _entries: list[CacheEntry] = field(default_factory=list)

    def get(self, query: str) -> dict | None:
        """Return cached response if single query exists, else NOne

        Steps:
            1. Normalize the incoming query
            2. Build its n-grm vector
            3. Compare against all the stored entries
            4. return the best match if above threshold
        """

        self._evict_expired()
        normalized = self._normalize(query)
        query_vector = self._build_ngram_vector(normalized)

        best_score = 0.0
        best_entry = None

        for entry in self._entries:
            score = self._cosine_similarity(query_vector, entry.ngram_vector)

            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= SIMILARITY_THRESHOLD and best_entry is not None:
            log.info(
                "semantic_cache.hit", query=query[:50], similarity=round(best_score, 4)
            )
            return best_entry.response

        log.info("semantic_cache.miss", query=query[:50])
        return None

    def set(self, query: str, response: dict) -> None:
        """Store a query response pair in the cache"""

        normalized = self._normalize(query)

        for entry in self._entries:
            if entry.normalized_query == normalized:
                return

        entry = CacheEntry(
            query=query,
            response=response,
            normalized_query=normalized,
            ngram_vector=self._build_ngram_vector(normalized),
            created_at=time.time(),
        )

        self._entries.append(entry)
        log.info(
            "semantic_cache.stored", query=query[:50], total_entries=len(self._entries)
        )

    def _evict_expired(self) -> None:
        """Remove entries older than CACHE_TTL_SECONDS"""
        cutoff = time.time() - CACHE_TTL_SECONDS
        self._entries = [e for e in self._entries if e.created_at > cutoff]

    @staticmethod
    def _normalize(query: str) -> str:
        """Lowercase, strip, collapse whitespace."""
        return " ".join(query.lower().split())

    @staticmethod
    def _build_ngram_vector(text: str) -> dict[str, int]:
        """Convert text to a frequency dict of character n-grams"""
        ngrams: dict[str, int] = {}
        for i in range(len(text) - NGRAM_SIZE + 1):
            ngram = text[i : i + NGRAM_SIZE]
            ngrams[ngram] = ngrams.get(ngram, 0) + 1
        return ngrams

    @staticmethod
    def _cosine_similarity(vec_a: dict[str, int], vec_b: dict[str, int]) -> float:
        """Compute cosine similarity between two frequency vectors.

        Formula: (A . B) / (||A|| * ||B||)

        Where:
          - A . B = sum of a[key] * b[key] for shared keys
          - ||A|| = sqrt(sum of a[key]^2)
        """
        dot_product = 0
        for key in vec_a:
            if key in vec_b:
                dot_product += vec_a[key] * vec_b[key]

        if dot_product == 0:
            return 0.0

        magnitude_a = math.sqrt(sum(v * v for v in vec_a.values()))
        magnitude_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)


cache = SemanticCache()
