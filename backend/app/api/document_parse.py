"""Parse API: a document's complete content as typed, source-located blocks
(source_structure/parse_view.py). Read only — a GET never extracts, OCRs,
rebuilds or stores anything.

Document isolation is the router's (core/document_access.py, as every
/{document_id} route); reading needs documents.view. Callers who cannot
export (export.read) get identifier shapes masked (core/masking.py), the
same shapes the logs never show in full.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.downloads import attachment_header, excel_csv
from app.core.auth import ActorContext, require_permission
from app.database.dependencies import get_database
from app.models.document import Document
from app.source_structure.parse_export import build_parse_csv, build_parse_xlsx, build_rows
from app.source_structure.parse_view import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, parse_document

router = APIRouter()


def _document(database: Session, document_id: str) -> Document:
    document = database.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def _file_stem(document: Document) -> str:
    return PurePath(document.original_filename or "document").stem


# A plain function: FastAPI runs it in its thread pool, so reading a long
# document's pages never blocks other requests.
@router.get("/{document_id}/parse")
def read_parse(
    document_id: str,
    start_page: int = Query(1, ge=1, description="First page of the window."),
    page_limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Pages per response."),
    database: Session = Depends(get_database),
    actor: ActorContext = Depends(require_permission("documents.view")),
) -> dict[str, Any]:
    """A window of pages, each whole: blocks in reading order (heading,
    paragraph, table, header, footer, page reference, marginalia), form
    boxes and tick boxes linked to their block, the numbered sections that
    start in the window, and per-page completeness. `window.next_start_page`
    pages through the rest; it is null on the last window."""

    return parse_document(
        database,
        _document(database, document_id),
        start_page=start_page,
        page_limit=page_limit,
        mask=not actor.has("export.read"),
    )


@router.get("/{document_id}/parse/export.xlsx")
def export_parse_xlsx(
    document_id: str,
    database: Session = Depends(get_database),
    actor: ActorContext = Depends(require_permission("export.read")),
) -> Response:
    """The whole parsed document in Excel, laid out as the original reads."""

    document = _document(database, document_id)
    stem = _file_stem(document)
    return Response(
        content=build_parse_xlsx(build_rows(database, document), document.original_filename or stem),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": attachment_header(f"{stem} - parsed.xlsx")},
    )


@router.get("/{document_id}/parse/export.csv")
def export_parse_csv(
    document_id: str,
    database: Session = Depends(get_database),
    actor: ActorContext = Depends(require_permission("export.read")),
) -> Response:
    """The whole parsed document as CSV, in the same rows as the Excel file."""

    document = _document(database, document_id)
    return Response(
        content=excel_csv(build_parse_csv(build_rows(database, document))),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment_header(f"{_file_stem(document)} - parsed.csv")},
    )
