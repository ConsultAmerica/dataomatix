"""Live smoke: Vercel frontend surfaces + Render API paths used by the UI."""

from __future__ import annotations

import json
import sys
import uuid
from io import BytesIO

import fitz
import httpx
from PIL import Image, ImageDraw, ImageFont

FRONTEND = "https://dataomatix.vercel.app"
API = "https://data-agent-backend-qbmc.onrender.com"
ORIGIN = FRONTEND


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

    client = httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0))

    for path in ["/", "/extraction/new", "/architecture"]:
        response = client.get(f"{FRONTEND}{path}", follow_redirects=True)
        check(f"Vercel {path}", response.status_code == 200, f"HTTP {response.status_code}")

    response = client.get(f"{API}/health", headers={"Origin": ORIGIN})
    check(
        "API /health",
        response.status_code == 200
        and response.json().get("status") in {"ok", "healthy"},
        response.text[:120],
    )
    acao = response.headers.get("access-control-allow-origin")
    check(
        "CORS ACAO for Vercel",
        acao in {ORIGIN, "*"},
        f"ACAO={acao}",
    )

    response = client.get(f"{API}/version")
    version = response.json()
    check("API /version", response.status_code == 200, json.dumps(version))

    response = client.get(f"{API}/ready")
    ready = response.json()
    check(
        "API /ready",
        response.status_code == 200 and ready.get("status") == "ready",
        f"git={(ready.get('git_sha') or '')[:12]} env={ready.get('environment')}",
    )

    marker = f"VRC-{uuid.uuid4().hex[:8].upper()}"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), f"Invoice Number: {marker}", fontsize=12)
    page.insert_text((72, 96), "Amount: $42,750.00", fontsize=12)
    page.insert_text((72, 120), "Date: 11/09/2026", fontsize=12)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    response = client.post(
        f"{API}/api/documents/upload",
        files={"file": (f"{marker}.pdf", pdf_bytes, "application/pdf")},
        headers={"Origin": ORIGIN},
    )
    body = response.json() if response.status_code in {200, 201} else {}
    check(
        "Upload PDF",
        response.status_code in {200, 201},
        f"HTTP {response.status_code} tier={body.get('size_tier')} job={body.get('processing_job_id')}",
    )
    doc_id = body.get("document_id")

    if doc_id:
        response = client.post(
            f"{API}/api/documents/{doc_id}/extract-pages",
            json={
                "run_ocr": True,
                "page_start": None,
                "page_end": None,
                "force_reprocess": False,
            },
        )
        check("Extract pages", response.status_code == 200, f"HTTP {response.status_code}")

        response = client.post(f"{API}/api/documents/{doc_id}/discover-schema")
        targets = (response.json() or {}).get("targets") or []
        keys = {item.get("key") for item in targets}
        check(
            "Discover schema fields",
            response.status_code == 200 and bool(targets),
            f"keys={sorted(keys)[:8]}",
        )
        check(
            "Invoice Number candidate",
            "invoice_number" in keys
            or any("invoice" in (item.get("label") or "").lower() for item in targets),
            str(sorted(keys)),
        )

    image = Image.new("RGB", (1100, 500), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    for index, line in enumerate(
        [
            "Invoice Number: ML-2026-4401",
            "Amount: $42,750.00",
            "Date: 11/09/2026",
            f"Nonce: {uuid.uuid4()}",
        ]
    ):
        draw.text((48, 48 + index * 56), line, fill="black", font=font)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    response = client.post(
        f"{API}/api/documents/upload",
        files={"file": ("mixed_language_latin.png", png, "image/png")},
        headers={"Origin": ORIGIN},
    )
    png_body = response.json() if response.status_code in {200, 201} else {}
    check(
        "Upload PNG",
        response.status_code in {200, 201},
        f"HTTP {response.status_code} status={png_body.get('status')}",
    )
    png_id = png_body.get("document_id")
    if png_id and png_body.get("status") != "duplicate_pending":
        response = client.post(
            f"{API}/api/documents/{png_id}/extract-pages",
            json={
                "run_ocr": True,
                "page_start": None,
                "page_end": None,
                "force_reprocess": True,
            },
        )
        check(
            "PNG extract/OCR",
            response.status_code == 200,
            f"HTTP {response.status_code}",
        )
        pages = client.get(f"{API}/api/documents/{png_id}/pages").json()
        text = (pages[0].get("final_text") or "") if pages else ""
        check(
            "PNG DocumentPage.text present",
            bool(text.strip()),
            f"chars={len(text)} sample={text[:80]!r}",
        )
        check(
            "PNG OCR has invoice token",
            "ML-2026-4401" in text.replace(" ", ""),
            text[:120].replace("\n", " | "),
        )
        response = client.post(f"{API}/api/documents/{png_id}/discover-schema")
        targets = (response.json() or {}).get("targets") or []
        keys = {item.get("key") for item in targets}
        check(
            "PNG schema Invoice/Amount/Date",
            {"invoice_number", "amount", "date"} <= keys
            or ("invoice_number" in keys and ("amount" in keys or "date" in keys)),
            f"keys={sorted(keys)}",
        )

    core = fitz.open()
    page = core.new_page()
    page.insert_text((72, 72), "medium pad")
    tiny = core.tobytes()
    core.close()
    pad = tiny + (b"\0" * (11 * 1024 * 1024 - len(tiny)))
    response = client.post(
        f"{API}/api/documents/upload",
        files={"file": ("pad-11mb.pdf", pad, "application/pdf")},
        headers={"Origin": ORIGIN},
    )
    medium = response.json() if response.status_code in {200, 201} else {}
    provenance = medium.get("ingestion_provenance") or {}
    check(
        "Medium upload background route",
        response.status_code == 201
        and medium.get("prefer_background") is True
        and medium.get("processing_job_id") is not None,
        (
            f"HTTP {response.status_code} tier={medium.get('size_tier')} "
            f"mode={provenance.get('processing_mode')} "
            f"job={medium.get('processing_job_id')}"
        ),
    )

    failed = [name for name, ok, _ in results if not ok]
    print("\n=== SUMMARY ===")
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
