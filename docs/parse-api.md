# Parse API

`GET /api/documents/{document_id}/parse?start_page=1&page_limit=10`

A document's complete content as typed, ordered, source-located blocks, read
from what is already stored. Implemented in `backend/app/api/document_parse.py`
(route) and `backend/app/source_structure/parse_view.py` (assembly).

## Guarantees

| Guarantee | How |
|---|---|
| Read only | No extraction, OCR or model call runs. The stored source structure is loaded, never rebuilt (`load`, not `get_or_build`); nothing is committed. A test patches every build path, OCR entry and `Session.commit` to fail and the GET still succeeds. |
| Same document, same run | `document.checksum_sha256` is the stored file; `run.structure.extractor_version` is the stored structure's. `run.structure.status` is `current`, `out_of_date` (shown as stored), `missing` or `unreadable`. |
| No invented positions | A block without a source box has `bbox: null` and a `locator` saying why (HTML, text-only page). |
| No silent loss | Each page reports `completeness`: printed characters on the page against characters held by its blocks, and the tokens missing (first 20). A table whose cells dropped printed words keeps those words in `table.source_lines` and lists them in `table.missing_in_cells`. A line whose display text dropped underline fill keeps its words in `raw_text`. |
| Unavailable ≠ empty | `elements: null` = no stored structure (unavailable); `[]` = none on this page. `sections.status`: `available` or `none`. |
| Paging | Pages come whole. `window.next_start_page` is the next request's `start_page`; `null` on the last window. `page_limit` 1–25 (default 10). Block ids (`p{page}.b{index}`) are stable across windows. |
| Access | Router-level document isolation (`enforce_document_access`, as every `/{document_id}` route) and `documents.view`. |
| Masking | Callers without `export.read` (the `viewer` role) get identifier shapes masked with `core/masking.redact_text` (SSN, 9+ digit runs, IBAN, MRZ) in every text field. Boxes, types and order are unchanged. No file path or URL to the stored original is returned. |

## Response

```jsonc
{
  "parse_version": 1,
  "document": { "id", "filename", "content_type", "source_type": "pdf|image|html",
                "checksum_sha256", "page_count", "processing_status" },
  "run": { "checksum_sha256",
           "structure": { "status": "current|out_of_date|missing|unreadable",
                          "extractor_version", "current_extractor_version" } },
  "window": { "start_page", "end_page", "page_limit", "next_start_page", "total_pages" },
  "pages": [{
    "page_number", "width", "height",            // PDF points; null for HTML
    "positioning": "spatial|text_only|none",
    "extraction_method": "native|ocr|dom|…",
    "blocks": [{
      "id": "p3.b7", "index": 7, "page": 3,
      "type": "heading|paragraph|table|header|footer|page_reference|marginalia",
      "source_kind": "heading|paragraph|table",  // reading-order kind; type is an additive label
      "text": "…verbatim…",
      "bbox": [x0, y0, x1, y1] | null,
      "lines": [{ "text", "bbox", "raw_text"? }],
      "table": null | { "headers", "rows", "candidate_id", "continues_from", "continues_to",
                        "source_lines"?, "missing_in_cells" },
      "locator": null | "why there is no box",
      "provenance": { "extraction_method", "positioning" }
    }],
    "elements": null | [{
      "id", "type": "form_field|checkbox", "item_number", "item_name", "item_parent", "item_sub",
      "label", "printed_value", "extracted_value", "reviewed_value", "blank", "choice",
      "review_status", "found_by", "label_bbox", "value_bbox", "block_id"
    }],
    "completeness": { "source_characters", "block_characters", "missing_characters",
                      "missing_tokens", "tables_with_cell_gaps", "complete", "note" }
  }],
  "sections": { "status": "available|none", "style": "far|numbered|none", "total",
                "rows": [{ "kind": "section|clause|paragraph", "level", "number", "heading", "page_start" }] },
  "masking": { "applied", "rule" },
  "warnings": ["…"]
}
```

## Download

`GET /api/documents/{document_id}/parse/export.xlsx` and `.../parse/export.csv`
(`source_structure/parse_export.py`) return the whole document, laid out as the
original reads: pages in order, each printed line on its own row, tables in real
cells. Each row carries its page, block number (counted through the document) and
block type. Built only from `parse_document`, so both are read only too. They need
`export.read` and are never masked. Printed words a table's cells lost, and words
not in any block, are written as notes rather than dropped.

## Where each part comes from

| Part | Source (existing code) |
|---|---|
| Words | `source_structure.service.page_words`: the stored file's text layer, or the page's persisted OCR word layer. |
| Blocks and reading order | `source_structure.reading_order.reconstruct_page` with the stored structure's accepted tables. |
| Tables | `StructuredSourceDocument.table_candidates` (stored), continuation links included. |
| Form fields, tick boxes | `original_layout.build_original_layout` over the loaded structure — the fields the Original File view shows. |
| Sections, clauses | `services.clause_outline.build_outline` over the stored page text — the rows `/clause-outline` returns. |
| Header, footer, page reference | Lines in the top or bottom tenth of the page that repeat (digits aside) on ≥3 pages or ≥30% of pages, read from the stored page text; page-number shapes. |
| Marginalia | "(End of clause / provision / section / part …)" lines, split out of the paragraph they close. |

## Limits

- HTML (FAR `part_52.html`) has no page coordinates: blocks are located by order only.
- A header, footer or end marker the page text does not repeat is not labelled; the block keeps its reading-order type.
- Form fields need a stored source structure; when it is missing they are `null`. The structure is built by the normal workspace path, never by Parse.
- No package splitting (not authorised).
