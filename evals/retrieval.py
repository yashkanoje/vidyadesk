"""Retrieval quality on the sample prospectus, with the real embedding model (local and free).

    python -m evals.retrieval
"""
import sys
import tempfile
import uuid
from pathlib import Path

import yaml
from fpdf import FPDF

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


def make_pdf(text_path, pdf_path):
    """A PDF copy of the prospectus, so retrieval is also measured on what owners usually upload."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, text_path.read_text(encoding="utf-8"))
    pdf.output(str(pdf_path))
    return pdf_path


def measure(document_path, cases):
    """Return (hits, answerable scores, unanswerable scores, missed questions) for one document."""
    with session_scope() as session:
        institute_id = add_institute(
            session,
            slug=f"retrieval-{uuid.uuid4().hex[:8]}",
            name="Retrieval test",
            facts=load_facts_file(EXAMPLES / "brightpath.yaml"),
            telegram_token="unused",
        ).id
        status = ingest(session, institute_id, document_path).status
    print(f"{document_path.name}: {status}")
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
    return hits, answerable, unanswerable, missed


def main() -> int:
    cases = yaml.safe_load((HERE / "retrieval.yaml").read_text(encoding="utf-8"))
    create_tables()
    text_path = EXAMPLES / "brightpath-prospectus.txt"
    worst = 1.0
    with tempfile.TemporaryDirectory() as folder:
        for path in (text_path, make_pdf(text_path, Path(folder) / "brightpath-prospectus.pdf")):
            hits, answerable, unanswerable, missed = measure(path, cases)
            rate = hits / len(answerable)
            worst = min(worst, rate)
            print(f"  expected passage in the top 3: {hits} of {len(answerable)} = {rate:.0%} (target {TARGET:.0%})")
            for question in missed:
                print(f"    missed: {question}")
            print(f"  best similarity, answerable: lowest {min(answerable):.4f}; unanswerable: highest {max(unanswerable):.4f}")
            print(f"  suggested RAG_MIN_SIMILARITY: {suggest_floor(answerable, unanswerable)}")
    return 0 if worst >= TARGET else 1


if __name__ == "__main__":
    sys.exit(main())
