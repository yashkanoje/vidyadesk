import pytest
from fpdf import FPDF
from sqlalchemy import func, select

from helpers import make_institute
from leadagent.rag.ingest import IngestError, ingest, main
from leadagent.store.models import Chunk, Document


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def make_pdf(path, text=None):
    pdf = FPDF()
    pdf.add_page()
    if text is not None:
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, text)
    pdf.output(str(path))
    return path


def test_a_text_pdf_is_split_embedded_and_stored(session, tmp_path):
    institute = make_institute(session)
    path = make_pdf(tmp_path / "prospectus.pdf", "Transport\n\nBuses run from Sector 19 every morning.")
    document = ingest(session, institute.id, path)
    session.commit()
    assert (document.filename, document.status) == ("prospectus.pdf", "ready")
    chunks = session.scalars(select(Chunk).where(Chunk.document_id == document.id)).all()
    assert "Sector 19" in " ".join(c.text for c in chunks)
    assert all(len(c.embedding) == 384 for c in chunks)


def test_a_pdf_with_no_text_is_marked_failed(session, tmp_path):
    institute = make_institute(session)
    document = ingest(session, institute.id, make_pdf(tmp_path / "scan.pdf"))
    session.commit()
    assert document.status == "failed" and "no text found" in document.error
    assert count(session, Chunk) == 0


def test_a_damaged_pdf_is_marked_failed(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF-1.4 this is not really a pdf")
    document = ingest(session, institute.id, path)
    assert document.status == "failed" and "could not read" in document.error


def test_text_and_markdown_files_are_accepted(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "faq.md"
    path.write_text("# Refunds\n\nFull refund within 7 days.", encoding="utf-8")
    assert ingest(session, institute.id, path).status == "ready"


def test_a_text_file_in_a_windows_code_page_is_still_added(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "notes.txt"
    path.write_bytes("Fees: ₹ shown as Rs. – café".encode("cp1252", errors="replace"))
    assert ingest(session, institute.id, path).status == "ready"


def test_adding_a_file_again_replaces_the_old_version(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "faq.txt"
    path.write_text("Old refund rule.", encoding="utf-8")
    ingest(session, institute.id, path)
    path.write_text("New refund rule.", encoding="utf-8")
    ingest(session, institute.id, path)
    session.commit()
    assert count(session, Document) == 1
    assert [c.text for c in session.scalars(select(Chunk))] == ["New refund rule."]


@pytest.mark.parametrize("name", ["photo.jpg", "notes.docx"])
def test_other_file_types_are_refused_before_anything_is_stored(session, tmp_path, name):
    institute = make_institute(session)
    path = tmp_path / name
    path.write_bytes(b"x")
    with pytest.raises(IngestError, match="only PDF"):
        ingest(session, institute.id, path)
    assert count(session, Document) == 0


def test_a_file_over_the_size_limit_is_refused(session, tmp_path, monkeypatch):
    institute = make_institute(session)
    monkeypatch.setattr("leadagent.rag.ingest.MAX_BYTES", 10)
    path = tmp_path / "big.txt"
    path.write_text("x" * 11, encoding="utf-8")
    with pytest.raises(IngestError, match="10 MB"):
        ingest(session, institute.id, path)


def test_the_command_line_adds_lists_and_deletes(session, tmp_path, capsys):
    make_institute(session)
    path = tmp_path / "faq.txt"
    path.write_text("Refunds within 7 days.", encoding="utf-8")
    assert main(["--institute", "bright", str(path)]) == 0
    assert main(["--institute", "bright", "--list"]) == 0
    out = capsys.readouterr().out
    assert "faq.txt" in out and "ready" in out
    document_id = session.scalars(select(Document)).one().id
    assert main(["--institute", "bright", "--delete", str(document_id)]) == 0
    assert count(session, Document) == 0 and count(session, Chunk) == 0


def test_the_command_line_reports_problems(session, tmp_path, capsys):
    make_institute(session)
    assert main(["--institute", "nobody", "--list"]) == 1
    assert main(["--institute", "bright", str(tmp_path / "missing.pdf")]) == 1
    assert main(["--institute", "bright", "--delete", "999"]) == 1
    err = capsys.readouterr().err
    assert "No institute" in err and "missing.pdf" in err and "No document 999" in err


def passages_of(session, document):
    return [c.text for c in session.scalars(select(Chunk).where(Chunk.document_id == document.id))]


def test_a_utf16_text_file_is_readable(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xff\xfe" + "Buses run from Sector 19.".encode("utf-16-le"))
    document = ingest(session, institute.id, path)
    session.commit()
    assert document.status == "ready"
    assert "Buses run from Sector 19" in " ".join(passages_of(session, document))


def test_a_utf8_bom_is_not_kept_in_the_first_passage(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xef\xbb\xbf" + b"Refunds within 7 days.")
    document = ingest(session, institute.id, path)
    session.commit()
    assert not passages_of(session, document)[0].startswith("\ufeff")


def test_nul_characters_are_removed_before_storing(session, tmp_path, monkeypatch):
    institute = make_institute(session)
    monkeypatch.setattr("leadagent.rag.ingest.extract_text", lambda path: "Fee\x00s are\x00 low.")
    path = tmp_path / "notes.txt"
    path.write_text("x", encoding="utf-8")
    document = ingest(session, institute.id, path)
    session.commit()
    assert passages_of(session, document) == ["Fees are low."]


def test_a_failed_replacement_keeps_the_old_version(session, tmp_path):
    institute = make_institute(session)
    path = tmp_path / "prospectus.txt"
    path.write_text("Old refund rule.", encoding="utf-8")
    old = ingest(session, institute.id, path)
    path.write_text("   ", encoding="utf-8")
    new = ingest(session, institute.id, path)
    session.commit()
    assert (old.status, new.status) == ("ready", "failed")
    assert passages_of(session, old) == ["Old refund rule."]
    assert count(session, Document) == 2
