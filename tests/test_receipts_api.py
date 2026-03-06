"""Integration tests for the Receipts API (upload + extraction)."""

import io
import os
import pytest


def _make_png_bytes():
    """Create a minimal valid 1×1 PNG in memory."""
    import struct, zlib
    def chunk(name, data):
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xFF\xFF\xFF")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def _make_pdf_bytes():
    """Create a minimal valid PDF with some receipt-like text."""
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj
4 0 obj<</Length 120>>
stream
BT /F1 12 Tf 50 700 Td (ACME SUPPLIES LTD) Tj 0 -20 Td (Date: 15/06/2024) Tj 0 -20 Td (Total GBP 45.00) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000315 00000 n 
trailer<</Size 5/Root 1 0 R>>
startxref
487
%%EOF"""
    return content


class TestReceiptUpload:
    def test_upload_png_creates_expense(self, client, db):
        data = {"file": (io.BytesIO(_make_png_bytes()), "receipt.png")}
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201
        body = res.get_json()
        assert "expense" in body
        assert body["expense"]["receipt_filename"] == "receipt.png"

    def test_upload_pdf_accepted(self, client, db):
        data = {"file": (io.BytesIO(_make_pdf_bytes()), "invoice.pdf")}
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201

    def test_upload_jpeg_accepted(self, client, db):
        # Use PNG bytes but .jpg extension – tests extension checking only
        data = {"file": (io.BytesIO(_make_png_bytes()), "receipt.jpg")}
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201

    def test_unsupported_format_rejected(self, client, db):
        data = {"file": (io.BytesIO(b"fake content"), "expense.xlsx")}
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        assert "error" in res.get_json()

    def test_no_file_returns_400(self, client, db):
        res = client.post("/api/receipts/upload", data={}, content_type="multipart/form-data")
        assert res.status_code == 400

    def test_file_stored_with_receipt_hash(self, client, db):
        data = {"file": (io.BytesIO(_make_png_bytes()), "hash_test.png")}
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        expense_id = res.get_json()["expense"]["id"]
        from app.models import Expense
        from app import db as _db
        with _db.session.no_autoflush:
            exp = _db.session.get(Expense, expense_id)
        assert exp.receipt_hash is not None
        assert len(exp.receipt_hash) == 64  # SHA-256 hex digest

    def test_attach_to_existing_expense(self, client, db, draft_expense):
        data = {
            "file": (io.BytesIO(_make_png_bytes()), "new_receipt.png"),
            "expense_id": str(draft_expense.id),
        }
        res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201
        assert res.get_json()["expense"]["id"] == draft_expense.id


class TestReceiptExtraction:
    def test_extract_no_receipt_returns_400(self, client, db, draft_expense):
        # draft_expense has no receipt file attached
        draft_expense.receipt_path = None
        from app import db as _db
        _db.session.commit()
        res = client.post(f"/api/receipts/{draft_expense.id}/extract")
        assert res.status_code == 400

    def test_extract_missing_expense_returns_404(self, client, db):
        res = client.post("/api/receipts/9999/extract")
        assert res.status_code == 404

    def test_extract_pdf_populates_fields(self, client, db):
        """Upload a PDF and extract; check that extracted_data is populated."""
        # Upload
        data = {"file": (io.BytesIO(_make_pdf_bytes()), "receipt.pdf")}
        upload_res = client.post(
            "/api/receipts/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert upload_res.status_code == 201
        expense_id = upload_res.get_json()["expense"]["id"]

        # Extract
        extract_res = client.post(f"/api/receipts/{expense_id}/extract")
        assert extract_res.status_code == 200
        body = extract_res.get_json()
        expense = body["expense"]
        # extracted_data should be populated
        assert expense["extracted_data"] is not None
        assert isinstance(expense["extracted_data"], dict)
