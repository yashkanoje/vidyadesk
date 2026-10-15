"""Text embeddings for document search. The model runs on this machine: no API key, no per-use cost."""
from functools import lru_cache
from pathlib import Path

MODEL = "BAAI/bge-small-en-v1.5"
DIMS = 384
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "models"  # data/ is git-ignored; about 70 MB


class FastEmbedder:
    def __init__(self):
        from fastembed import TextEmbedding  # imported here: it is slow to load, and tests use a fake

        self._model = TextEmbedding(model_name=MODEL, cache_dir=str(CACHE_DIR))

    def passages(self, texts):
        return [vector.tolist() for vector in self._model.embed(list(texts))]

    def query(self, text):
        return self.passages([text])[0]


@lru_cache
def get_embedder():
    return FastEmbedder()
