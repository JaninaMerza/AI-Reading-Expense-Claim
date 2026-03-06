"""Receipts API routes – upload and extraction."""

import os
import uuid

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app import db
from app.models import Expense
from app.services.receipt_extractor import extract_receipt_data

receipts_bp = Blueprint("receipts", __name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@receipts_bp.route("/upload", methods=["POST"])
def upload_receipt():
    """
    AC-1: Upload a receipt file attached to an (optionally existing) expense.

    Accepts multipart/form-data with:
        file       – the receipt file (PDF / JPG / PNG)
        expense_id – optional; ID of an existing draft expense to attach to

    Returns the expense record with a 201 status.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not _allowed_file(file.filename):
        return jsonify(
            {
                "error": (
                    f"Unsupported file type. Allowed formats: "
                    f"{', '.join(sorted(ALLOWED_EXTENSIONS)).upper()}."
                )
            }
        ), 400

    # Save file with a unique name to prevent collisions
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    safe_name = secure_filename(unique_name)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    filepath = os.path.join(upload_folder, safe_name)
    file.save(filepath)

    # Compute hash for duplicate detection
    file_hash = Expense.compute_file_hash(filepath)

    # Attach to existing expense or create a new draft
    expense_id = request.form.get("expense_id")
    if expense_id:
        expense = db.get_or_404(Expense, int(expense_id))
        # Remove old file if replacing
        if expense.receipt_path and os.path.exists(expense.receipt_path):
            try:
                os.remove(expense.receipt_path)
            except OSError:
                pass
    else:
        expense = Expense()
        db.session.add(expense)

    expense.receipt_filename = file.filename
    expense.receipt_path = filepath
    expense.receipt_hash = file_hash
    db.session.commit()

    return jsonify(
        {
            "message": "Receipt uploaded successfully.",
            "expense": expense.to_dict(),
        }
    ), 201


@receipts_bp.route("/<int:expense_id>/extract", methods=["POST"])
def extract_receipt(expense_id):
    """
    AC-2: Extract structured data from the uploaded receipt using OCR / AI.

    Populates the expense's vendor, transaction_date, amount, tax_amount, and
    currency fields from the extracted data.  Fields that cannot be extracted
    with high confidence are listed in extraction_flags.
    """
    expense = db.get_or_404(Expense, expense_id)

    if not expense.receipt_path or not os.path.exists(expense.receipt_path):
        return jsonify({"error": "No receipt file found for this expense."}), 400

    data = extract_receipt_data(expense.receipt_path)

    import json

    expense.extracted_data = json.dumps(data)
    expense.extraction_flags = json.dumps(data.get("flags", []))

    # Populate fields only if not already manually set
    overrides = expense.get_manual_overrides()

    if "vendor" not in overrides and data.get("vendor"):
        expense.vendor = data["vendor"]
    if "transaction_date" not in overrides and data.get("transaction_date"):
        from datetime import date as _date
        expense.transaction_date = _date.fromisoformat(data["transaction_date"])
    if "amount" not in overrides and data.get("amount") is not None:
        expense.amount = data["amount"]
    if "tax_amount" not in overrides and data.get("tax_amount") is not None:
        expense.tax_amount = data["tax_amount"]
    if "currency" not in overrides and data.get("currency"):
        expense.currency = data["currency"]

    db.session.commit()

    return jsonify(
        {
            "message": "Receipt data extracted successfully.",
            "expense": expense.to_dict(),
        }
    )
