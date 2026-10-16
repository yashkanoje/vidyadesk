from sqlalchemy import func, select

from helpers import FakeEmbedder, add_document_with_chunks, make_institute
from leadagent.store import repo
from leadagent.store.models import Chunk, Document, Institute


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_nearest_chunks_rank_by_meaning_inside_one_institute(session):
    mine = make_institute(session, "mine")
    theirs = make_institute(session, "theirs")
    add_document_with_chunks(session, mine, "prospectus.txt", ["bus transport from sector 19", "refund policy for fees"])
    add_document_with_chunks(session, theirs, "other.txt", ["bus transport from sector 19 every morning"])
    rows = repo.nearest_chunks(session, mine.id, FakeEmbedder().query("bus from sector 19"), 5)
    assert rows[0][0].text == "bus transport from sector 19"
    assert {filename for _, _, filename in rows} == {"prospectus.txt"}
    assert rows[0][1] <= rows[-1][1]  # nearest first


def test_passages_of_a_failed_document_are_never_returned(session):
    institute = make_institute(session)
    document = add_document_with_chunks(session, institute, "x.txt", ["bus transport"])
    repo.mark_document_failed(session, document, "broken")
    session.commit()
    assert repo.nearest_chunks(session, institute.id, FakeEmbedder().query("bus"), 5) == []


def test_passages_keep_the_text_order(session):
    institute = make_institute(session)
    document = add_document_with_chunks(session, institute, "x.txt", ["first", "second", "third"])
    chunks = session.scalars(select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.position)).all()
    assert [(c.position, c.text) for c in chunks] == [(0, "first"), (1, "second"), (2, "third")]


def test_deleting_a_document_removes_its_passages(session):
    institute = make_institute(session)
    document = add_document_with_chunks(session, institute, "x.txt", ["a", "b"])
    repo.delete_document(session, document)
    session.commit()
    assert count(session, Document) == 0 and count(session, Chunk) == 0


def test_deleting_an_institute_removes_its_documents_and_passages(session):
    institute = make_institute(session)
    add_document_with_chunks(session, institute, "x.txt", ["a"])
    session.delete(session.get(Institute, institute.id))
    session.commit()
    assert count(session, Document) == 0 and count(session, Chunk) == 0


def test_documents_are_scoped_to_their_institute(session):
    one = make_institute(session, "one")
    two = make_institute(session, "two")
    mine = add_document_with_chunks(session, one, "a.txt", ["x"])
    add_document_with_chunks(session, two, "a.txt", ["y"])
    assert [d.filename for d in repo.documents_for(session, one.id)] == ["a.txt"]
    assert repo.get_document(session, two.id, mine.id) is None
    assert [d.id for d in repo.documents_named(session, one.id, "a.txt")] == [mine.id]
