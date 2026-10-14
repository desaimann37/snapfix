"""Text embeddings: local BAAI/bge-small-en-v1.5 (384-d) with a deterministic hashing fallback.

The hashing embedder is used in tests (no model download, no internet) and automatically if the
sentence-transformers model cannot be loaded, so the app never fails to start because of embeddings.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Any, Protocol

import numpy as np

from app.config import get_settings
from app.models import EMBED_DIM

log = logging.getLogger(__name__)

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray: ...


_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "is", "are", "was", "were", "it", "its",
    "this", "that", "there", "with", "for", "from", "by", "be", "been", "has", "have", "had", "i", "we",
    "my", "our", "near", "into", "very", "just", "so", "but", "not", "no", "again", "please", "room",
}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


class HashEmbedder:
    """Feature-hashing embedder over stemmed unigrams, bigrams and character trigrams."""

    name = "hash-384"

    def _features(self, text: str) -> list[tuple[str, float]]:
        words = [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]
        feats: list[tuple[str, float]] = [(f"w:{w}", 1.0) for w in words]
        feats += [(f"b:{a}_{b}", 0.7) for a, b in zip(words, words[1:])]
        for w in words:
            padded = f"#{w}#"
            feats += [(f"c:{padded[i:i + 3]}", 0.25) for i in range(len(padded) - 2)]
        return feats

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), EMBED_DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat, weight in self._features(text or ""):
                digest = hashlib.md5(feat.encode()).digest()
                idx = int.from_bytes(digest[:4], "little") % EMBED_DIM
                sign = 1.0 if digest[4] & 1 else -1.0
                out[row, idx] += sign * weight
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class LocalEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        try:  # use the cached copy without network round-trips; download only the first time
            self._model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        except Exception:
            self._model = SentenceTransformer(model_name, device="cpu")
        self._lock = threading.Lock()

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        if query:
            texts = [BGE_QUERY_PREFIX + t for t in texts]
        with self._lock:
            vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def _load_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_backend == "hash":
        return HashEmbedder()
    try:
        embedder = LocalEmbedder(settings.embedding_model)
        log.info("embeddings: loaded %s", settings.embedding_model)
        return embedder
    except Exception as exc:  # pragma: no cover - depends on environment
        log.warning("embeddings: could not load %s (%s); falling back to hashing embedder",
                    settings.embedding_model, exc)
        return HashEmbedder()


def get_embedder() -> Embedder:
    """Load once; concurrent callers (warm-up thread + first request) wait for the same load."""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = _load_embedder()
    return _embedder


def embedder_status() -> str:
    """Name of the loaded embedder, or 'loading' (doesn't trigger a model load)."""
    return _embedder.name if _embedder is not None else "loading"


def embed_one(text: str, *, query: bool = False) -> list[float]:
    return get_embedder().embed([text], query=query)[0].tolist()


def embed_many(texts: list[str], *, query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    return get_embedder().embed(texts, query=query).tolist()


def as_np(vec: Any) -> np.ndarray | None:
    if vec is None:
        return None
    return np.asarray(vec, dtype=np.float32)


def cosine(a: Any, b: Any) -> float:
    va, vb = as_np(a), as_np(b)
    if va is None or vb is None:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / denom) if denom else 0.0


def ticket_embedding_text(title: str, summary: str, category: str, asset_type: str | None) -> str:
    """The text we embed for duplicate detection / clustering (spec 7.3 step 1)."""
    parts = [title, summary, category.replace("_", " ")]
    if asset_type:
        parts.append(asset_type)
    return ". ".join(p for p in parts if p)
