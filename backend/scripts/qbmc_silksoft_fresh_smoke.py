"""Decisive qbmc OCR gate: fresh JPG upload (not the sticky Silksoft row)."""

from __future__ import annotations

import json
import sys
import uuid
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFont

BASE = "https://dataomatix-backend.onrender.com"


def _font(size: int = 28):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def silksoft_like_jpg() -> bytes:
    image = Image.new("RGB", (1400, 1800), "white")
    draw = ImageDraw.Draw(image)
    title = _font(36)
    body = _font(28)
    lines = [
        ("SILKSOFT TECHNOLOGIES", title),
        ("Business Promotion & Internet Business Solutions", body),
        ("", body),
        ("TO WHOM IT MAY CONCERN", body),
        ("", body),
        (
            "This is certified that Mr Asif Kamran s/o Mr. Noor Khan had worked",
            body,
        ),
        (
            "in Silksoft Technologies as a Web and Software Developer from",
            body,
        ),
        ("Dec 15, 2001 to June 30, 2003.", body),
        ("", body),
        ("Date: 03/04/2003", body),
        ("Ref. No.: CS-14/05", body),
        (f"Nonce: {uuid.uuid4()}", body),
    ]
    y = 80
    for text, font in lines:
        draw.text((72, y), text, fill="black", font=font)
        y += 48 if text else 24
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def main() -> int:
    client = httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0))

    version = client.get(f"{BASE}/version").json()
    print("version", json.dumps(version))
    ready = client.get(f"{BASE}/ready").json()
    ocr = (ready.get("checks") or {}).get("ocr_diagnostics") or {}
    print(
        "ocr_binaries",
        ocr.get("tesseract_binary"),
        ocr.get("tessdata_prefix_env"),
        "legacy",
        ready.get("legacy_office_conversion"),
    )

    payload = silksoft_like_jpg()
    name = f"Silksoft-fresh-{uuid.uuid4().hex[:8]}.jpg"
    upload = client.post(
        f"{BASE}/api/documents/upload",
        files={"file": (name, payload, "image/jpeg")},
    )
    print("upload", upload.status_code, upload.text[:240])
    upload.raise_for_status()
    body = upload.json()
    doc_id = body["document_id"]
    print("document_id", doc_id)

    extract = client.post(
        f"{BASE}/api/documents/{doc_id}/extract-pages",
        json={
            "run_ocr": True,
            "page_start": None,
            "page_end": None,
            "force_reprocess": False,
        },
    )
    print("extract", extract.status_code)
    extract_body = extract.json()
    print(
        json.dumps(
            {
                k: extract_body.get(k)
                for k in (
                    "status",
                    "ocr_required_pages",
                    "ocr_completed_pages",
                    "page_text_chars",
                    "warnings",
                )
            },
            indent=2,
        )
    )
    extract.raise_for_status()

    page = client.get(f"{BASE}/api/documents/{doc_id}/pages").json()[0]
    page_view = {
        "ocr_attempted": page.get("ocr_attempted"),
        "ocr_succeeded": page.get("ocr_succeeded"),
        "ocr_error": page.get("ocr_error"),
        "character_count": page.get("character_count"),
        "final_text_chars": len(page.get("final_text") or ""),
        "final_text_sample": (page.get("final_text") or "")[:180],
    }
    print("page", json.dumps(page_view, indent=2))

    discover = client.post(f"{BASE}/api/documents/{doc_id}/discover-schema")
    discover.raise_for_status()
    targets = discover.json().get("targets") or []
    print("targets", len(targets), [t.get("key") for t in targets[:8]])

    ok = (
        page_view["ocr_attempted"] is True
        and page_view["ocr_succeeded"] is True
        and page_view["final_text_chars"] > 0
        and len(targets) > 0
    )
    print("GATE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
