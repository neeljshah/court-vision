"""scripts.platformkit.knowledge.retrieve -- offline hybrid retrieval over the vault.

Baseline (installed deps only: numpy, scipy, pandas, sklearn):
  Dense lane : TfidfVectorizer word (1,2)-gram, sublinear_tf -> cosine (dense-ish).
  Sparse lane: TfidfVectorizer word (1,1)-gram, sublinear_tf -> cosine (BM25-like).
  Fusion     : Reciprocal Rank Fusion (RRF) over the two lanes' rank lists.
  Boost      : exact title/category token overlap adds a bonus post-RRF.
  Floor      : best ABSOLUTE raw cosine < RELEVANCE_TAU -> honest-reject (empty hits).
  Store      : numpy/scipy matrix + parquet. 4K notes is tiny; NO LanceDB needed.

PLUGGABLE upgrades (OPTIONAL; pip-installs we do NOT run here -- see config.py):
EmbeddingBackend (bge/voyage), Reranker (bge-reranker-v2-m3), lancedb store, Haiku
contextual prefixes. The ABCs below let them drop in later.
HARD BOUNDARY: returns cited TEXT/snippets only -- never a probability/odds/ROI/edge.
"""
from __future__ import annotations

import abc
import json
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

from . import config
from .text_utils import stem_tokenizer


@dataclass
class Hit:
    note_id: str
    sport: str
    category: str
    title: str
    snippet: str
    citation: str        # "[[note_id]]" ready to drop into cited markdown
    score: float = 0.0   # fused RRF+boost RELEVANCE rank -- never a prediction
    related: List[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    hits: List[Hit]
    query: str
    sport: Optional[str]
    reject: bool         # True when nothing cleared the relevance floor
    reject_message: str = "No relevant intel found."


class EmbeddingBackend(abc.ABC):
    """Swap-in dense lane (bge/voyage). Baseline = stored TF-IDF vectorizer."""

    @abc.abstractmethod
    def transform(self, texts: Sequence[str]) -> np.ndarray: ...

    @property
    @abc.abstractmethod
    def model_id(self) -> str: ...


class Reranker(abc.ABC):
    """Swap-in cross-encoder rerank over the RRF candidate pool (bge-reranker)."""

    @abc.abstractmethod
    def rerank(self, query: str, hits: List[Hit]) -> List[Hit]: ...


class IdentityReranker(Reranker):
    """Baseline: keep RRF+boost order. bge-reranker drops in here later."""

    def rerank(self, query: str, hits: List[Hit]) -> List[Hit]:
        return sorted(hits, key=lambda h: -h.score)

@dataclass
class IndexState:
    """df + fitted dense/sparse vectorizers + L2-normed matrices (cosine == dot)."""
    df: pd.DataFrame
    dense_vec: object
    dense_mat: np.ndarray
    sparse_vec: object
    sparse_mat: object
    manifest: dict


_STATE: Optional[IndexState] = None


def _load_state(index_dir: Path = config.INDEX_DIR) -> IndexState:
    corpus = index_dir / "corpus.parquet"
    if not corpus.exists():
        raise FileNotFoundError(
            f"Index not built at {index_dir}. Run:\n"
            "  python -m scripts.platformkit.knowledge.index --build")
    df = pd.read_parquet(corpus)
    dense_vec = pickle.loads(config.TFIDF_DENSE_PKL.read_bytes())
    sparse_vec = pickle.loads(config.TFIDF_SPARSE_PKL.read_bytes())
    dense_mat = np.load(config.VECTORS_NPY)
    sparse_mat = normalize(sparse_vec.transform(df["embed_text"].tolist()), norm="l2")
    manifest = (json.loads(config.MANIFEST_PATH.read_text(encoding="ascii"))
                if config.MANIFEST_PATH.exists() else {})
    return IndexState(df=df, dense_vec=dense_vec, dense_mat=dense_mat,
                      sparse_vec=sparse_vec, sparse_mat=sparse_mat, manifest=manifest)


def get_state(index_dir: Path = config.INDEX_DIR, force: bool = False) -> IndexState:
    global _STATE
    if _STATE is None or force:
        _STATE = _load_state(index_dir)
    return _STATE


def reset_state() -> None:
    """Drop the cached index (tests / after a refresh)."""
    global _STATE
    _STATE = None


def _cosine_rows(qvec, mat, rows: np.ndarray, dense: bool) -> np.ndarray:
    qn = normalize(qvec, norm="l2")
    if dense:
        return mat[rows] @ np.asarray(qn.todense()).ravel().astype(np.float32)
    return np.asarray((mat[rows] @ qn.T).todense()).ravel()


def _top_n(sim: np.ndarray, n: int) -> List[int]:
    if sim.shape[0] <= n:
        return list(np.argsort(-sim))
    part = np.argpartition(-sim, n)[:n]
    return list(part[np.argsort(-sim[part])])


def _rrf(dense_order: List[int], sparse_order: List[int],
         dense_w: float, sparse_w: float, k: int) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for rank, idx in enumerate(dense_order):
        out[idx] = out.get(idx, 0.0) + dense_w / (k + rank + 1)
    for rank, idx in enumerate(sparse_order):
        out[idx] = out.get(idx, 0.0) + sparse_w / (k + rank + 1)
    return out


def _boost(qtoks: set, title: str, category: str) -> float:
    """Boost proportional to the fraction of query tokens in the title (4/5 beats
    1/5); category overlap adds a small flat bonus. Capped by config."""
    if not qtoks:
        return 0.0
    ttoks = set(stem_tokenizer(title))
    ctoks = set(stem_tokenizer(category))
    frac = len(qtoks & ttoks) / len(qtoks)
    b = config.TITLE_BOOST * frac
    if qtoks & ctoks:
        b += config.CATEGORY_BOOST
    return b


_H1_LINE = re.compile(r"^#\s+.*$", re.MULTILINE)
_BOILER = re.compile(r"^>.*$", re.MULTILINE)        # markets-efficient blockquote
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)  # strip ## Summary etc markers


def _snippet(body: str, n: int = config.SNIPPET_CHARS) -> str:
    """One-line snippet: drop H1 + boilerplate blockquote + heading markers, take n
    chars on a word boundary."""
    txt = _H1_LINE.sub("", body)
    txt = _BOILER.sub("", txt)
    txt = _HEADING.sub("", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) <= n:
        return txt
    cut = txt[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut) + "..."


def _row_to_hit(r, score: float) -> Hit:
    nid = str(r["note_id"])
    rel = r["related"]
    rel = list(rel) if isinstance(rel, (list, np.ndarray)) else []
    return Hit(note_id=nid, sport=str(r["sport"]), category=str(r["category"]),
               title=str(r["title"]), snippet=_snippet(str(r["body"])),
               citation=f"[[{nid}]]", score=score, related=rel)


def retrieve(
    query: str,
    sport: Optional[str] = None,
    category: Optional[str] = None,
    top_k: int = config.TOP_K,
    tau: float = config.RELEVANCE_TAU,
    *,
    dense_w: float = config.DENSE_W,
    sparse_w: float = config.SPARSE_W,
    use_boost: bool = True,
    reranker: Optional[Reranker] = None,
    min_raw: Optional[float] = None,
    index_dir: Path = config.INDEX_DIR,
) -> RetrievalResult:
    """Hybrid dense+sparse -> RRF -> exact boost -> floor. Honest-reject when the best
    raw cosine < the gate (`tau`/`min_raw`). Ablation knobs drive the golden ladder."""
    state = get_state(index_dir)
    df = state.df

    mask = np.ones(len(df), dtype=bool)
    if sport:
        mask &= (df["sport"].str.upper() == sport.upper()).to_numpy()
    if category:
        mask &= (df["category"].str.lower() == category.lower()).to_numpy()
    rows = np.where(mask)[0]
    if rows.size == 0:
        return RetrievalResult([], query, sport, reject=True)

    pool_n = min(config.RETRIEVE_POOL, rows.size)
    qd = state.dense_vec.transform([query])
    qs = state.sparse_vec.transform([query])
    dense_sim = _cosine_rows(qd, state.dense_mat, rows, dense=True)
    sparse_sim = _cosine_rows(qs, state.sparse_mat, rows, dense=False)

    # Absolute relevance gate (store-agnostic) -> honest-reject; `tau` drives it.
    gate = min_raw if min_raw is not None else tau
    if max(float(dense_sim.max()), float(sparse_sim.max())) < gate:
        return RetrievalResult([], query, sport, reject=True)

    # dense-only / sparse-only ablation branches skip the fusion.
    if sparse_w <= 0.0:
        fused = {i: float(dense_sim[i]) for i in _top_n(dense_sim, pool_n)}
    elif dense_w <= 0.0:
        fused = {i: float(sparse_sim[i]) for i in _top_n(sparse_sim, pool_n)}
    else:
        fused = _rrf(_top_n(dense_sim, pool_n), _top_n(sparse_sim, pool_n),
                     dense_w, sparse_w, config.RRF_K)

    pool = sorted(fused, key=lambda i: -fused[i])[:config.RERANK_POOL]
    if not pool:
        return RetrievalResult([], query, sport, reject=True)

    top_score = max(fused[i] for i in pool) or 1.0  # normalize fused to 0..1
    qtoks = set(stem_tokenizer(query))
    hits: List[Hit] = []
    for li in pool:
        r = df.iloc[int(rows[li])]
        score = fused[li] / top_score
        if use_boost:
            score += _boost(qtoks, str(r["title"]), str(r["category"]))
        hits.append(_row_to_hit(r, float(score)))

    hits = (reranker or IdentityReranker()).rerank(query, hits)
    kept = [h for h in hits if h.score >= config.RANK_FLOOR][:top_k]
    if not kept:
        return RetrievalResult([], query, sport, reject=True)
    return RetrievalResult(kept, query, sport, reject=False)


def related_nodes(note_id: str, hops: int = config.GRAPH_HOPS,
                  index_dir: Path = config.INDEX_DIR) -> List[Hit]:
    """Follow parsed ## Related wikilinks `hops` deep -> graph neighbours as Hits."""
    state = get_state(index_dir)
    df = state.df
    by_stem: Dict[str, int] = {}
    for i, nid in enumerate(df["note_id"]):
        by_stem.setdefault(str(nid).split("/")[-1], i)
    seen, frontier, out = {note_id}, [note_id], []
    for _ in range(max(1, hops)):
        nxt: List[str] = []
        for cur in frontier:
            sub = df[df["note_id"] == cur]
            if sub.empty:
                continue
            rel = sub.iloc[0]["related"]
            rel = list(rel) if isinstance(rel, (list, np.ndarray)) else []
            for stem in rel:
                gi = by_stem.get(str(stem).split("/")[-1])
                if gi is None or str(df.iloc[gi]["note_id"]) in seen:
                    continue
                r = df.iloc[gi]
                seen.add(str(r["note_id"]))
                nxt.append(str(r["note_id"]))
                out.append(_row_to_hit(r, 0.0))
        frontier = nxt
    return out


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="Retrieve smoke test")
    ap.add_argument("query", nargs="+")
    ap.add_argument("--sport", default=None)
    args = ap.parse_args()
    res = retrieve(" ".join(args.query), sport=args.sport)
    if res.reject:
        print("HONEST REJECT:", res.reject_message)
    for i, h in enumerate(res.hits, 1):
        print(f"[{i}] ({h.score:.3f}) {h.citation} -- {h.title}")
