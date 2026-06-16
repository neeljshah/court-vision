"""scripts.platformkit.knowledge.index -- build / refresh the offline vault index.

Ingests vault/_Organized/{NBA,MLB,Soccer,Tennis} + _Index + the auto-memory dir
(via ingest.build_corpus) and fits TWO sklearn TF-IDF lanes:

  dense lane : word (1,2)-gram, sublinear_tf  -> L2-normed float32 matrix (cosine)
  sparse lane: word (1,1)-gram, sublinear_tf  -> BM25-like keyword matrix (cosine)

Writes (all under data/index/vault/, gitignored):
  corpus.parquet      NoteChunk records (note_id, sport, category, title, tags,
                      body, related, contextual, embed_text, content_sha256, ...)
  vectors_dense.npy   (N, V) L2-normed float32 dense matrix
  tfidf_dense.pkl     fitted dense TfidfVectorizer (transforms queries)
  tfidf_sparse.pkl    fitted sparse TfidfVectorizer (transforms queries)
  manifest.json       build stats, model ids, sha map size, last_refresh

Both matrices are ALWAYS rebuilt from the full corpus in one pass so the two
lanes never drift out of sync (a hybrid-rot gotcha). A .lock file in INDEX_DIR
serializes builds (no concurrent rebuilds).

OPTIONAL upgrades (documented; not installed): a neural EmbeddingBackend / bge
Reranker / LanceDB store / Haiku contextual prefixes -- see config.py + retrieve.py.

HARD BOUNDARY: this layer informs synthesis/narration only; nothing numeric here
enters a Brier-scored path. ASCII only. Per-file test: tests/test_index.py
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from . import config
from .ingest import NoteChunk, build_corpus, save_corpus_parquet


def fit_lanes(texts: List[str]):
    """Fit dense + sparse TF-IDF lanes. Returns (dense_vec, dense_arr, sparse_vec)."""
    dense_vec = TfidfVectorizer(**config.TFIDF_DENSE_PARAMS)
    dense_mat = dense_vec.fit_transform(texts)
    dense_arr = normalize(dense_mat, norm="l2").astype(np.float32).toarray()
    sparse_vec = TfidfVectorizer(**config.TFIDF_SPARSE_PARAMS)
    sparse_vec.fit(texts)
    return dense_vec, dense_arr, sparse_vec


def _acquire_lock():
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    lf = open(config.LOCK_FILE, "w")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lf.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lf.close()
        raise RuntimeError("Index build already running (data/index/vault/.lock).")
    lf.write(str(os.getpid()))
    lf.flush()
    return lf


def _release_lock(lf) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            lf.seek(0)
            msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lf, fcntl.LOCK_UN)
    except OSError:
        pass
    lf.close()


def _write_manifest(chunks: List[NoteChunk], dense_vec, sparse_vec,
                    dense_arr: np.ndarray, elapsed: float) -> None:
    per_source: dict = {}
    for c in chunks:
        per_source[c.sport] = per_source.get(c.sport, 0) + 1
    manifest = {
        "embed_backend": config.EMBED_BACKEND,
        "embed_model_id": config.EMBED_MODEL_ID if config.EMBED_BACKEND != "tfidf"
        else "tfidf-word-12-sublinear",
        "ctx_prefix_backend": config.CTX_PREFIX_BACKEND,
        "ctx_model_id": config.CTX_MODEL_ID if config.CTX_PREFIX_BACKEND == "haiku"
        else "n/a (offline template)",
        "reranker_backend": config.RERANKER_BACKEND,
        "note_count": len(chunks),
        "per_source": per_source,
        "dense_vocab": len(dense_vec.vocabulary_),
        "sparse_vocab": len(sparse_vec.vocabulary_),
        "dense_shape": list(dense_arr.shape),
        "relevance_tau": config.RELEVANCE_TAU,
        "rrf": {"k": config.RRF_K, "dense_w": config.DENSE_W,
                "sparse_w": config.SPARSE_W},
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_elapsed_s": round(elapsed, 2),
    }
    config.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="ascii")


def build(refresh: bool = False, verbose: bool = False) -> dict:
    """Cold build or sha-aware refresh. Returns the written manifest dict."""
    t0 = time.time()
    lf = _acquire_lock()
    try:
        old_shas: dict = {}
        if refresh and config.CORPUS_PARQUET.exists():
            import pandas as pd
            prev = pd.read_parquet(config.CORPUS_PARQUET,
                                   columns=["note_id", "content_sha256"])
            old_shas = dict(zip(prev["note_id"], prev["content_sha256"]))

        chunks = build_corpus()
        if not chunks:
            raise RuntimeError("No notes found; check config.VAULT_ROOT / MEMORY_DIR.")

        if refresh and verbose:
            changed = sum(1 for c in chunks
                          if old_shas.get(c.note_id) != c.content_sha256)
            print(f"[index] changed/new since last build: {changed}/{len(chunks)}")

        texts = [c.embed_text for c in chunks]
        dense_vec, dense_arr, sparse_vec = fit_lanes(texts)

        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        save_corpus_parquet(chunks, config.CORPUS_PARQUET)
        np.save(str(config.VECTORS_NPY), dense_arr)
        with open(config.TFIDF_DENSE_PKL, "wb") as fh:
            pickle.dump(dense_vec, fh, protocol=4)
        with open(config.TFIDF_SPARSE_PKL, "wb") as fh:
            pickle.dump(sparse_vec, fh, protocol=4)
        elapsed = time.time() - t0
        _write_manifest(chunks, dense_vec, sparse_vec, dense_arr, elapsed)
        print(f"[index] built {len(chunks)} notes, dense={dense_arr.shape}, "
              f"{elapsed:.1f}s -> {config.INDEX_DIR}")
        return json.loads(config.MANIFEST_PATH.read_text(encoding="ascii"))
    finally:
        _release_lock(lf)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build/refresh the vault knowledge index.")
    ap.add_argument("--build", action="store_true", help="Cold build (default).")
    ap.add_argument("--refresh", action="store_true", help="sha-aware refresh.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    build(refresh=args.refresh, verbose=args.verbose)
