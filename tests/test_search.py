from helpers import add_document_with_chunks, make_institute
from leadagent.rag.search import Passage, search
from leadagent.settings import get_settings

PASSAGES = ["refund policy full refund within 7 days", "bus transport from sector 19", "weekly tests every sunday"]


def test_search_returns_the_closest_passages_first(session):
    institute = make_institute(session)
    add_document_with_chunks(session, institute, "prospectus.txt", PASSAGES)
    results = search(session, institute.id, "bus from sector 19", k=2, min_similarity=0.0)
    assert len(results) == 2
    assert results[0] == Passage("prospectus.txt", "bus transport from sector 19", results[0].similarity)
    assert results[0].similarity >= results[1].similarity


def test_passages_below_the_floor_are_dropped(session):
    institute = make_institute(session)
    add_document_with_chunks(session, institute, "prospectus.txt", PASSAGES)
    assert search(session, institute.id, "hostel rooms and mess food", min_similarity=0.5) == []


def test_search_never_returns_another_institutes_passages(session):
    mine = make_institute(session, "mine")
    theirs = make_institute(session, "theirs")
    add_document_with_chunks(session, theirs, "theirs.txt", PASSAGES)
    assert search(session, mine.id, "bus from sector 19", min_similarity=0.0) == []


def test_the_default_floor_comes_from_the_settings(session, monkeypatch):
    institute = make_institute(session)
    add_document_with_chunks(session, institute, "prospectus.txt", ["bus transport"])
    monkeypatch.setattr(get_settings(), "rag_min_similarity", 0.99)
    assert search(session, institute.id, "bus timings") == []
    monkeypatch.setattr(get_settings(), "rag_min_similarity", 0.0)
    assert search(session, institute.id, "bus timings") != []
