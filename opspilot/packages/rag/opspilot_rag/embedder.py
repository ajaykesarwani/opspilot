"""Embedders.

`HashingEmbedder` is a deterministic, offline, zero-cost embedder based on feature hashing of
stemmed word unigrams (bigrams were measured on the golden set and hurt short queries). Unlike
random vectors it carries a real, lexical similarity signal, so retrieval quality and the
abstention threshold can be measured meaningfully in CI without an API key. It does NOT
understand meaning ("refund" vs "money back"); a real embedding model is the upgrade path.
`MockEmbedder` is kept as a backwards-compatible alias.
"""

import hashlib
import math
import re
from collections import Counter
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "you",
        "your",
        "tell",
        "me",
        "about",
    ]
)


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _stem(token: str) -> str:
    # Deliberately tiny: enough to match "refund"/"refunds" without a NLP dependency.
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class HashingEmbedder:
    """Deterministic bag-of-words embedder (signed feature hashing, L2-normalised)."""

    def __init__(self, dimension: int = 512) -> None:
        if dimension < 8:
            raise ValueError("dimension must be >= 8")
        self.dimension = dimension

    def _features(self, text: str) -> Counter[str]:
        return Counter(tokenize(text))

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for feature, count in self._features(text).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if (value >> 63) & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            # No usable tokens: a fixed unit vector keeps Chroma's cosine space happy while
            # scoring ~0 against everything real, so such inputs end up abstaining.
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


# Backwards-compatible name used across the codebase and tests.
MockEmbedder = HashingEmbedder
