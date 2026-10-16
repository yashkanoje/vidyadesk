"""Add an institute's documents to what the agent can search.

    python -m leadagent.rag.ingest --institute brightpath examples/brightpath-prospectus.txt
    python -m leadagent.rag.ingest --institute brightpath --list
    python -m leadagent.rag.ingest --institute brightpath --delete 3
"""
import argparse
import sys
from pathlib import Path

from pypdf import PdfReader

from leadagent.rag import embed
from leadagent.rag.chunk import chunk_text
from leadagent.store import repo
from leadagent.store.db import create_tables, session_scope

MAX_BYTES = 10 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md"}


class IngestError(ValueError):
    """The file was refused before anything was stored. The message is safe to show to an owner."""


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        text = "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    else:
        data = path.read_bytes()
        encoding = "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
        text = data.decode(encoding, errors="replace")
    return text


def ingest(session, institute_id, path):
    path = Path(path)
    if path.suffix.lower() not in TEXT_SUFFIXES | {".pdf"}:
        raise IngestError(f"{path.name}: only PDF, .txt and .md files are accepted")
    if path.stat().st_size > MAX_BYTES:
        raise IngestError(f"{path.name} is larger than 10 MB")
    old_versions = repo.documents_named(session, institute_id, path.name)
    error, passages = None, []
    try:
        passages = chunk_text(extract_text(path).replace("\x00", ""))  # PostgreSQL text cannot hold NUL
    except Exception as exc:  # a damaged or password-protected PDF
        error = f"could not read the file ({type(exc).__name__})"
    if not error and not passages:
        # shortcut: scanned PDFs are refused, add OCR when an institute's brochure is a scan (spec Section 15)
        error = "no text found (a scanned PDF needs OCR, which is not supported yet)"
    if error:  # the old version, if any, keeps working
        document = repo.add_document(session, institute_id, path.name)
        repo.mark_document_failed(session, document, error)
        return document
    for old in old_versions:  # a new version replaces the old one
        repo.delete_document(session, old)
    document = repo.add_document(session, institute_id, path.name)
    repo.add_chunks(session, document, passages, embed.get_embedder().passages(passages))
    return document


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="leadagent.rag.ingest")
    parser.add_argument("--institute", required=True, help="the institute's slug")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("file", nargs="?", help="a PDF, .txt or .md file to add")
    action.add_argument("--list", action="store_true", help="list this institute's documents")
    action.add_argument("--delete", type=int, metavar="DOCUMENT_ID", help="delete a document and its passages")
    args = parser.parse_args(argv)

    create_tables()
    with session_scope() as session:
        institute = repo.institute_by_slug(session, args.institute)
        if institute is None:
            print(f"Error: No institute with slug {args.institute!r}", file=sys.stderr)
            return 1
        if args.list:
            for document in repo.documents_for(session, institute.id):
                reason = f"  ({document.error})" if document.error else ""
                print(f"{document.id}  {document.filename}  {document.status}{reason}")
            return 0
        if args.delete is not None:
            document = repo.get_document(session, institute.id, args.delete)
            if document is None:
                print(f"Error: No document {args.delete} for this institute", file=sys.stderr)
                return 1
            repo.delete_document(session, document)
            print(f"Document {args.delete} and its passages are deleted.")
            return 0
        try:
            document = ingest(session, institute.id, args.file)
        except (IngestError, FileNotFoundError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        reason = f" ({document.error})" if document.error else ""
        print(f"Added {document.filename} as document {document.id}: {document.status}{reason}")
        return 0 if document.status == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
