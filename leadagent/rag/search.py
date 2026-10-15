from dataclasses import dataclass

from leadagent.rag import embed
from leadagent.settings import get_settings
from leadagent.store import repo


@dataclass(frozen=True)
class Passage:
    document: str  # the file it came from
    text: str
    similarity: float  # cosine similarity to the question; 1.0 means the same meaning


def search(session, institute_id, query, k=4, min_similarity=None):
    """This institute's passages nearest in meaning to the query, best first, above the similarity floor."""
    floor = get_settings().rag_min_similarity if min_similarity is None else min_similarity
    vector = embed.get_embedder().query(query)
    passages = [
        Passage(filename, chunk.text, 1.0 - distance)
        for chunk, distance, filename in repo.nearest_chunks(session, institute_id, vector, k)
    ]
    return [p for p in passages if p.similarity >= floor]
