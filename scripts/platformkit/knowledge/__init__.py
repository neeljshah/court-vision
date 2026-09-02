"""scripts.platformkit.knowledge -- offline-first vault RAG layer.

Baseline: sklearn TfidfVectorizer (word-ngram dense-ish + sublinear_tf sparse),
fused via RRF, with title/category boost and honest-reject floor.

Pluggable upgrade path (pip-install required, never auto-installed):
  EmbeddingBackend:  swap TF-IDF for bge-m3 / voyage-3 / text-embedding-3-large
  Reranker:          swap identity for BAAI/bge-reranker-v2-m3 / cross-encoder
  Vector store:      swap numpy cosine for LanceDB (lancedb>=0.5) once corpus
                     grows beyond ~50K notes (current ~4K, numpy is instant).

HARD BOUNDARY: this layer emits text + citations ONLY.
It never outputs a probability, odds, ROI, or edge signal.
"""
