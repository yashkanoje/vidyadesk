"""Retrieval quality on the sample prospectus, with the real embedding model (local and free).

    python -m evals.retrieval
"""
import sys
import uuid
from pathlib import Path

import yaml

from evals.checks import passage_hit, suggest_floor
from leadagent.cli import add_institute
from leadagent.facts import load_facts_file
from leadagent.rag.ingest import ingest
from leadagent.rag.search import search
from leadagent.store import repo
from leadagent.store.db import create_tables, session_scope

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"
TARGET = 0.8


def main() -> int:
    cases = yaml.safe_load((HERE / "retrieval.yaml").read_text(encoding="utf-8"))
    create_tables()
    with session_scope() as session:
        institute_id = add_institute(
            session,
            slug=f"retrieval-{uuid.uuid4().hex[:8]}",
            name="Retrieval test",
            facts=load_facts_file(EXAMPLES / "brightpath.yaml"),
            telegram_token="unused",
        ).id
        status = ingest(session, institute_id, EXAMPLES / "brightpath-prospectus.txt").status
    print(f"prospectus: {status}")
    hits, answerable, unanswerable, missed = 0, [], [], []
    try:
        with session_scope() as session:
            for case in cases:
                passages = search(session, institute_id, case["question"], k=3, min_similarity=0.0)
                top = passages[0].similarity if passages else 0.0
                if case["expect"] is None:
                    unanswerable.append(top)
                    continue
                answerable.append(top)
                if passage_hit([p.text for p in passages], case["expect"]):
                    hits += 1
                else:
                    missed.append(case["question"])
    finally:
        with session_scope() as session:
            session.delete(repo.get_institute(session, institute_id))  # its documents and passages go with it
    rate = hits / len(answerable)
    print(f"expected passage in the top 3: {hits} of {len(answerable)} = {rate:.0%} (target {TARGET:.0%})")
    for question in missed:
        print(f"  missed: {question}")
    print(f"best similarity, questions the prospectus answers: lowest {min(answerable):.3f}")
    print(f"best similarity, questions it does not answer:   highest {max(unanswerable):.3f}")
    print(f"suggested RAG_MIN_SIMILARITY: {suggest_floor(answerable, unanswerable)}")
    return 0 if rate >= TARGET else 1


if __name__ == "__main__":
    sys.exit(main())
