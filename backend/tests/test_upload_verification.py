"""Increment 7.3.4 step 2 — upload verification beyond tests/test_upload_validation.py
(which covers corrupt and password-protected PDFs, ZIP/email refusal and
duplicate holding): every format's empty and damaged files, disguised
executables, the size limit, mixed text/scanned pages, one page failing
while the others are read, and the original file kept byte for byte.

A refused upload states its cause and leaves nothing behind: no document,
no stored file, nothing for a later upload to be matched against.
"""

from __future__ import annotations

import hashlib
import io
from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_page import DocumentPage

client = TestClient(app)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(content: bytes, suffix: str, mime: str, **params):
    name = f"verify-{uuid4().hex[:8]}{suffix}"
    return client.post("/api/documents/upload", files={"file": (name, content, mime)}, params=params)


def _image(fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 60), "white").save(buffer, format=fmt)
    return buffer.getvalue()


def _pdf(*texts: str | None) -> bytes:
    """One page per entry: its text, or None for an image-only page."""

    doc = fitz.open()
    for text in texts:
        page = doc.new_page()
        if text is None:
            pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 80), 0)
            pixmap.clear_with(255)
            page.insert_image(fitz.Rect(72, 72, 472, 232), pixmap=pixmap)
        else:
            page.insert_text((72, 72), text)
    return doc.tobytes()


def _documents_with(checksum: str) -> list[Document]:
    database = SessionLocal()
    try:
        return list(database.scalars(select(Document).where(Document.checksum_sha256 == checksum)))
    finally:
        database.close()


def _refused(response, *words: str) -> None:
    assert response.status_code in (400, 413, 415, 422), (response.status_code, response.text[:200])
    detail = str(response.json().get("detail")).lower()
    assert any(word in detail for word in words), detail


# --- empty and content-free files ---------------------------------------------------------

EMPTY = [
    (".pdf", PDF), (".docx", DOCX), (".xlsx", XLSX), (".csv", "text/csv"), (".txt", "text/plain"),
    (".html", "text/html"), (".png", "image/png"), (".jpg", "image/jpeg"),
]


@pytest.mark.parametrize(("suffix", "mime"), EMPTY, ids=[s for s, _ in EMPTY])
def test_an_empty_file_is_refused(suffix, mime) -> None:
    _refused(_upload(b"", suffix, mime), "empty")


@pytest.mark.parametrize(("content", "suffix", "mime"), [
    (b"   \n\n\t  \r\n", ".txt", "text/plain"),
    (b"<html><body>  <p> </p>  </body></html>", ".html", "text/html"),
    (b"\n\n,,\n,,\n", ".csv", "text/csv"),
], ids=["txt", "html", "csv"])
def test_a_text_file_with_nothing_to_read_is_refused_and_leaves_nothing(content, suffix, mime) -> None:
    _refused(_upload(content, suffix, mime), "no readable text")
    assert _documents_with(hashlib.sha256(content).hexdigest()) == []


# --- damaged files ------------------------------------------------------------------------

DAMAGED = [
    (b"\x89PNG\r\n\x1a\n" + b"not image data" * 12, ".png", "image/png"),
    (_image("PNG")[:60], ".png", "image/png"),  # a real PNG cut off
    (b"\xff\xd8\xff\xe0" + b"not image data" * 12, ".jpg", "image/jpeg"),
    (_image("TIFF")[:40], ".tiff", "image/tiff"),
    (b"PK\x03\x04" + b"\x00" * 60, ".xlsx", XLSX),
    (b"PK\x03\x04" + b"\x00" * 60, ".docx", DOCX),
]


@pytest.mark.parametrize(("content", "suffix", "mime"), DAMAGED,
                         ids=["png-garbage", "png-truncated", "jpg-garbage", "tiff-truncated", "xlsx", "docx"])
def test_a_damaged_file_is_refused_with_its_cause(content, suffix, mime) -> None:
    _refused(_upload(content, suffix, mime), "damaged", "valid", "corrupt", "incomplete", "can't be read")
    assert _documents_with(hashlib.sha256(content).hexdigest()) == []


def test_bytes_that_arent_html_are_refused_not_a_server_error_and_leave_no_duplicate() -> None:
    """Binary data named .html once failed as "could not be stored securely"
    (500) after its record was saved — and the same bytes uploaded again
    were then held as a duplicate of that failed upload."""

    content = bytes(range(256)) * 4 + uuid4().bytes
    response = _upload(content, ".html", "text/html")
    _refused(response, "could not be read as html")
    assert _documents_with(hashlib.sha256(content).hexdigest()) == []
    again = _upload(content, ".html", "text/html")
    assert again.status_code != 200 or again.json().get("status") != "duplicate_pending"


def test_a_valid_image_is_still_accepted() -> None:
    for fmt, suffix, mime in (("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg"), ("TIFF", ".tiff", "image/tiff")):
        response = _upload(_image(fmt), suffix, mime, allow_duplicate="true")
        assert response.status_code == 201, (fmt, response.text[:200])


# --- wrong types --------------------------------------------------------------------------

MZ = b"MZ\x90\x00" + b"\x00" * 120


@pytest.mark.parametrize(("content", "suffix", "mime"), [
    (MZ, ".exe", "application/x-msdownload"),
    (b"alert(1)", ".js", "application/javascript"),
    (MZ, ".pdf", PDF),
    (MZ, ".docx", DOCX),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, ".pdf", PDF),
], ids=["exe", "js", "exe-as-pdf", "exe-as-docx", "png-as-pdf"])
def test_an_unsupported_or_disguised_file_is_refused(content, suffix, mime) -> None:
    _refused(_upload(content, suffix, mime), "unsupported", "signature", "not")


def test_a_content_type_that_contradicts_the_extension_is_refused() -> None:
    _refused(_upload(_pdf("Contract"), ".pdf", "image/png"), "content type")


def test_a_generic_content_type_is_accepted_when_the_bytes_match() -> None:
    assert _upload(_pdf(f"Contract {uuid4()}"), ".pdf", "application/octet-stream").status_code == 201


def test_a_password_protected_pdf_is_refused() -> None:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Confidential")
    content = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    _refused(_upload(content, ".pdf", PDF), "password", "encrypt")


# --- size ---------------------------------------------------------------------------------


def test_a_file_over_the_size_limit_is_refused_and_not_kept(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_mb", 0.01)  # 10 KB
    content = _pdf(*(f"Page {i} {uuid4().hex * 40}" for i in range(60)))
    assert len(content) > 0.01 * 1024 * 1024
    _refused(_upload(content, ".pdf", PDF), "size")
    assert _documents_with(hashlib.sha256(content).hexdigest()) == []


# --- what is recorded and kept ----------------------------------------------------------------


def test_the_original_file_is_kept_unchanged_with_its_fingerprint() -> None:
    content = _pdf(f"Original {uuid4()}", "Second page")
    response = _upload(content, ".pdf", PDF)
    assert response.status_code == 201
    body = response.json()
    assert body["checksum_sha256"] == hashlib.sha256(content).hexdigest()
    assert body["size_bytes"] == len(content)
    assert body["page_count"] == 2
    assert body["content_type"] == PDF
    database = SessionLocal()
    try:
        document = database.get(Document, body["document_id"])
        stored = get_settings().upload_path / document.stored_filename
        assert stored.read_bytes() == content
    finally:
        database.close()


def test_mixed_text_and_scanned_pages_are_told_apart() -> None:
    response = _upload(_pdf(f"Typed page {uuid4()} with enough words to be read natively.", None), ".pdf", PDF)
    document_id = response.json()["document_id"]
    assert client.post(f"/api/documents/{document_id}/extract-pages", json={"run_ocr": False}).status_code == 200
    database = SessionLocal()
    try:
        pages = {p.page_number: p for p in database.scalars(select(DocumentPage).where(DocumentPage.document_id == document_id))}
    finally:
        database.close()
    assert not pages[1].requires_ocr and pages[1].final_text.strip()
    assert pages[2].requires_ocr


def test_one_page_failing_leaves_the_others_read_and_is_reported(monkeypatch) -> None:
    import app.services.document_extraction as extraction

    real = extraction.extract_page

    def failing(**kwargs):
        if kwargs["page_index"] == 1:  # page 2
            raise RuntimeError("simulated page failure")
        return real(**kwargs)

    monkeypatch.setattr(extraction, "extract_page", failing)
    response = _upload(_pdf(f"First {uuid4()}", "Second", "Third"), ".pdf", PDF)
    document_id = response.json()["document_id"]
    result = client.post(f"/api/documents/{document_id}/extract-pages", json={"run_ocr": False})
    assert result.status_code == 200, result.text[:200]
    database = SessionLocal()
    try:
        document = database.get(Document, document_id)
        numbers = set(database.scalars(select(DocumentPage.page_number).where(DocumentPage.document_id == document_id)))
    finally:
        database.close()
    assert numbers == {1, 3}
    # Never reported as a clean completion.
    assert document.processing_status == "completed_with_warnings"
