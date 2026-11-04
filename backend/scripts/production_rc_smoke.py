"""Production release-candidate smoke.

Proves the production topology gate:
  upload → persist → extract → reopen → edit → export → oracle preview

Requires the RC API surface to be deployed (export, extracted_value, audit actors).
Optional: RC_SMOKE_BEARER / RC_SMOKE_ACTOR_ID when production RBAC is enforced.

  python backend/scripts/production_rc_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any

import fitz
import httpx

BASE = os.environ.get("RC_SMOKE_BASE", "https://data-agent-backend-qbmc.onrender.com")
FRONTEND = os.environ.get("RC_SMOKE_FRONTEND", "https://dataomatix.vercel.app")


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    bearer = os.environ.get("RC_SMOKE_BEARER", "").strip()
    actor = os.environ.get("RC_SMOKE_ACTOR_ID", "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if actor:
        headers["X-Actor-Id"] = actor
    return headers


def _require(response: httpx.Response, label: str) -> Any:
    if response.status_code >= 400:
        raise AssertionError(
            f"{label} failed: {response.status_code} {response.text[:500]}"
        )
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.content


def main() -> None:
    headers = _auth_headers()
    client = httpx.Client(base_url=BASE, timeout=180.0, headers=headers)
    gate: dict[str, str] = {}

    print("=== RC smoke against", BASE, "===")
    if headers:
        print("   auth headers present:", ", ".join(headers.keys()))
    else:
        print("   auth: none (ok if RBAC not enforced on this deploy)")

    # --- Cold start observation (API) ---
    print("1) cold-start /health (may take 30–90s on Render free)")
    t0 = time.perf_counter()
    try:
        response = client.get("/health")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        _require(response, "health")
        assert response.headers.get("x-request-id")
        gate["cold_start_api"] = f"PASS ({elapsed_ms}ms, req={response.headers.get('x-request-id')})"
        print("   ok", elapsed_ms, "ms", response.headers.get("x-request-id"))
        if response.headers.get("x-content-type-options") == "nosniff":
            gate["security_headers"] = "PASS"
        else:
            gate["security_headers"] = "WARN (nosniff missing — older deploy?)"
    except Exception as exc:  # noqa: BLE001
        gate["cold_start_api"] = f"FAIL ({exc})"
        raise

    print("2) /ready + deployment fingerprint")
    ready = _require(client.get("/ready"), "ready")
    assert ready["status"] == "ready"
    assert ready["checks"]["database"]["status"] == "ok"
    gate["ready"] = "PASS"

    version = _require(client.get("/version"), "version")
    live_sha = (ready.get("git_sha") or version.get("git_sha") or "").strip()
    live_env = (ready.get("environment") or version.get("environment") or "").strip()
    expected_sha = (
        os.environ.get("RC_EXPECTED_GIT_SHA")
        or os.environ.get("GIT_SHA")
        or ""
    ).strip()
    print(
        "   git_sha=",
        live_sha,
        "environment=",
        live_env,
        "rbac_enforced=",
        ready.get("rbac_enforced"),
        "entra=",
        ready.get("entra_configured"),
    )
    if not live_sha or live_sha == "unknown":
        gate["fingerprint"] = "FAIL (git_sha missing)"
        raise AssertionError("Production /ready|/version missing git_sha fingerprint.")
    if expected_sha and not (
        live_sha.startswith(expected_sha[:7]) or expected_sha.startswith(live_sha[:7])
    ):
        gate["fingerprint"] = f"FAIL (live={live_sha} expected={expected_sha})"
        raise AssertionError(
            f"Deployed git_sha {live_sha} does not match expected {expected_sha}."
        )
    if live_env.lower() != "production":
        gate["fingerprint"] = f"FAIL (environment={live_env!r}, want production)"
        raise AssertionError(
            f"Production environment must report 'production', got {live_env!r}."
        )
    gate["fingerprint"] = f"PASS ({live_sha[:12]} / {live_env})"

    if "rbac_enforced" not in ready:
        gate["rc_api_surface"] = "FAIL (/ready missing rbac_enforced — RC not deployed)"
        raise AssertionError(
            "Production /ready does not expose rbac_enforced. "
            "Deploy the RC commit before tagging v1.0.0."
        )

    marker = f"RC-{uuid.uuid4().hex[:8].upper()}"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), f"Contract Number: {marker}", fontsize=10)
    page.insert_text((72, 92), "Total Amount: $120,000", fontsize=10)
    page.insert_text((72, 112), "Payment Terms: Net 30", fontsize=10)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    print("3) fresh upload", marker)
    upload = _require(
        client.post(
            "/api/documents/upload",
            files={"file": (f"{marker}.pdf", pdf_bytes, "application/pdf")},
        ),
        "upload",
    )
    document_id = upload["document_id"]
    gate["fresh_upload"] = "PASS"
    print("   document_id", document_id)

    print("4) extract-pages (persist source)")
    _require(
        client.post(
            f"/api/documents/{document_id}/extract-pages",
            json={
                "run_ocr": False,
                "page_start": None,
                "page_end": None,
                "force_reprocess": False,
            },
        ),
        "extract-pages",
    )
    pages = _require(client.get(f"/api/documents/{document_id}/pages"), "pages")
    assert pages, "expected persisted pages"
    gate["persistent_source"] = f"PASS ({len(pages)} pages)"

    print("5) discover-schema")
    discover = _require(
        client.post(f"/api/documents/{document_id}/discover-schema"),
        "discover-schema",
    )
    targets = discover["targets"]
    field_ids = [
        item["id"]
        for item in targets
        if item.get("target_type") != "table" and item.get("source_examples")
    ][:8]
    assert field_ids, "expected evidence-backed field targets"

    print("6) extract job")
    start = _require(
        client.post(
            f"/api/documents/{document_id}/jobs/extract",
            json={"target_ids": field_ids, "use_ai_fallback": True},
        ),
        "start extract",
    )
    job_id = start["id"]
    job = None
    for _ in range(120):
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in ("complete", "failed"):
            break
        time.sleep(1)
    assert job and job["status"] == "complete", job
    scalars = job["result"]["scalars"]
    assert scalars
    sample = next(
        (item for item in scalars if item.get("normalized_key") == "total_amount"),
        scalars[0],
    )
    key = sample["normalized_key"]
    original_value = sample.get("value")
    for field in ("value", "confidence", "validation", "retrieval", "evidence"):
        assert sample.get(field) is not None or field == "retrieval", sample
    assert sample.get("evidence", {}).get("page_number")
    gate["extraction"] = f"PASS ({len(scalars)} scalars, sample={key})"
    print("   sample", key, sample.get("extraction_method"), "value=", original_value)

    print("7) reopen extract-results")
    reopen = _require(
        client.get(f"/api/documents/{document_id}/extract-results"),
        "extract-results",
    )
    match = next(
        item for item in reopen["scalars"] if item["normalized_key"] == key
    )
    assert match.get("value") == original_value
    # RC fields — fail if undeployed
    if "extracted_value" not in match and "review_status" not in match:
        gate["reopen"] = "FAIL (missing extracted_value/review_status — RC undeployed)"
        raise AssertionError(
            "extract-results missing RC governance fields. Deploy RC before v1.0.0."
        )
    gate["reopen"] = "PASS"
    print(
        "   extracted_value=",
        match.get("extracted_value"),
        "value=",
        match.get("value"),
        "review_status=",
        match.get("review_status"),
    )

    print("8) edit field + durable machine/reviewed split")
    edited_value = "$125,000"
    edit = client.post(
        f"/api/documents/{document_id}/targets/{key}/corrections",
        json={
            "action": "edit",
            "original_value": original_value,
            "corrected_value": edited_value,
            "changed_by": "rc-smoke@consultamerica",
        },
    )
    if edit.status_code == 401:
        gate["governance_edit"] = "FAIL (401 — need RC_SMOKE_BEARER / actor under RBAC)"
        raise AssertionError(
            "Edit returned 401. Set RC_SMOKE_BEARER or RC_SMOKE_ACTOR_ID for RBAC."
        )
    _require(edit, "edit")
    edit_req = edit.headers.get("x-request-id")
    after = _require(
        client.get(f"/api/documents/{document_id}/extract-results"),
        "reopen-after-edit",
    )
    edited = next(item for item in after["scalars"] if item["normalized_key"] == key)
    assert edited.get("value") == edited_value, edited
    machine = edited.get("extracted_value")
    assert machine in {original_value, str(original_value)}, (
        f"extracted_value should remain machine original; got {machine!r}"
    )
    assert edited.get("review_status") == "edited"
    gate["governance_edit"] = f"PASS (req={edit_req})"
    print("   value=", edited["value"], "extracted_value=", machine, "req=", edit_req)

    print("9) export JSON + CSV")
    export = client.get(f"/api/documents/{document_id}/export")
    _require(export, "export json")
    fields = export.json()["fields"]
    row = next((item for item in fields if item.get("field_key") == key), fields[0])
    for required in (
        "field",
        "extracted_value",
        "value",
        "review_status",
        "validation",
        "source",
    ):
        assert required in row, row
    assert row["value"] == edited_value
    assert row["extracted_value"] in {original_value, str(original_value), machine}

    csv_resp = client.get(f"/api/documents/{document_id}/export.csv")
    _require(csv_resp, "export csv")
    csv_text = csv_resp.text
    assert "value" in csv_text.splitlines()[0]
    assert edited_value in csv_text
    gate["export"] = "PASS"
    print("   json+csv ok")

    print("10) oracle preview gate")
    oracle = client.get(f"/api/documents/{document_id}/oracle-payload")
    body = _require(oracle, "oracle-payload")
    assert body.get("send_allowed") is False
    assert "pending" in (body.get("excluded_statuses") or [])
    # Edited field may be authoritative; pending others skipped
    for item in body.get("fields") or []:
        assert item["review_status"] in {"accepted", "edited"}, item
    for item in body.get("skipped") or []:
        assert item["review_status"] in {"pending", "rejected", "unknown"}, item
    gate["oracle_preview"] = (
        f"PASS (auth={body.get('authoritative_count')} skip={body.get('skipped_count')})"
    )
    print("  ", gate["oracle_preview"])

    print("11) source render (evidence)")
    page_no = edited.get("page") or edited.get("evidence", {}).get("page_number") or 1
    render = client.get(
        f"/api/documents/{document_id}/pages/{page_no}/render",
        params={"highlight": str(edited.get("extracted_value") or "")[:80]},
    )
    render_body = _require(render, "page render")
    assert isinstance(render_body, dict)
    assert (render_body.get("image_data_url") or "").startswith("data:image/")
    gate["source_verification"] = "PASS"

    print("\n=== GATE SUMMARY ===")
    for name, status in gate.items():
        print(f"  {name:24} {status}")

    print(
        "\nRC SMOKE PASS",
        json.dumps(
            {
                "document_id": document_id,
                "marker": marker,
                "frontend_reopen": f"{FRONTEND}/extraction/new?documentId={document_id}&focus={key}",
                "repository_hint": f"{FRONTEND}/repository",
                "architecture": f"{FRONTEND}/architecture",
                "manual_remaining": [
                    "UI cold-start: first upload after idle should retry gracefully",
                    "Render logs: request_id/stages/durations; no page text/prompts/secrets",
                    f"Repository UI reopen + View Source for {document_id}",
                ],
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("RC SMOKE FAIL:", exc, file=sys.stderr)
        raise SystemExit(1) from exc
