import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from helpers import make_institute, make_user
from leadagent.app import app
from leadagent.dashboard.routes import safe_filename
from leadagent.store.models import Chunk, Document


@pytest.fixture
def client(session):
    make_user(session, institute=make_institute(session, "bright"))
    make_institute(session, "other")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    return test_client


def upload(client, name, data, slug="bright"):
    return client.post(f"/dash/{slug}/documents", files={"file": (name, data, "text/plain")}, follow_redirects=True)


def test_uploading_a_text_file_adds_a_ready_document(client, session):
    page = upload(client, "faq.txt", b"Refunds within 7 days.")
    assert "Added faq.txt" in page.text and "ready" in page.text
    document = session.scalars(select(Document)).one()
    assert document.filename == "faq.txt" and document.status == "ready"


@pytest.mark.parametrize("name, stored", [("../../evil.txt", "evil.txt"), ("..\\..\\evil.txt", "evil.txt"), ("dir/faq.md", "faq.md")])
def test_a_path_in_the_filename_is_stripped(name, stored):
    assert safe_filename(name) == stored


@pytest.mark.parametrize("name", ["", ".", "..", "   "])
def test_an_empty_or_dot_filename_is_refused(name):
    assert safe_filename(name) is None


def test_a_refused_upload_stores_nothing(client, session):
    page = upload(client, "photo.jpg", b"x")
    assert "only PDF" in page.text
    assert session.scalars(select(Document)).all() == []


def test_an_upload_over_the_limit_is_refused(client, session, monkeypatch):
    monkeypatch.setattr("leadagent.dashboard.routes.MAX_BYTES", 10)
    page = upload(client, "big.txt", b"x" * 11)
    assert "larger than 10 MB" in page.text
    assert session.scalars(select(Document)).all() == []


def test_deleting_a_document_removes_its_passages(client, session):
    upload(client, "faq.txt", b"Refunds within 7 days.")
    document = session.scalars(select(Document)).one()
    client.post(f"/dash/bright/documents/{document.id}/delete")
    session.expire_all()
    assert session.scalars(select(Document)).all() == [] and session.scalars(select(Chunk)).all() == []


def test_another_institutes_documents_are_out_of_reach(client, session):
    from helpers import add_document_with_chunks
    from leadagent.store import repo

    theirs = repo.institute_by_slug(session, "other")
    document = add_document_with_chunks(session, theirs, "secret.txt", ["their passage"])
    assert client.get("/dash/other/documents").status_code == 404
    assert upload(client, "faq.txt", b"x", slug="other").status_code == 404
    assert client.post(f"/dash/bright/documents/{document.id}/delete").status_code == 404
    assert "secret.txt" not in client.get("/dash/bright/documents").text
