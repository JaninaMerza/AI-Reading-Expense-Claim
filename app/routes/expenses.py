"""Expenses API routes – CRUD, validation, and submission."""

import json
from datetime import date

from flask import Blueprint, jsonify, request

from app import db
from app.models import Expense, Job
from app.services.expense_validator import check_duplicate_receipt, validate_expense

expenses_bp = Blueprint("expenses", __name__)


@expenses_bp.route("/", methods=["GET"])
def list_expenses():
    status = request.args.get("status")
    job_id = request.args.get("job_id")
    query = Expense.query
    if status:
        query = query.filter_by(status=status)
    if job_id:
        query = query.filter_by(job_id=int(job_id))
    expenses = query.order_by(Expense.created_at.desc()).all()
    return jsonify([e.to_dict() for e in expenses])


@expenses_bp.route("/<int:expense_id>", methods=["GET"])
def get_expense(expense_id):
    expense = db.get_or_404(Expense, expense_id)
    return jsonify(expense.to_dict())


@expenses_bp.route("/", methods=["POST"])
def create_expense():
    """Create a new draft expense (without a receipt – use /receipts/upload first)."""
    data = request.get_json(force=True)
    expense = _apply_fields(Expense(), data)
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201


@expenses_bp.route("/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    """
    AC-3: Update / manually override extracted expense fields.

    All fields provided in the request body are treated as manual overrides
    and recorded in manual_overrides for audit purposes.
    """
    expense = db.get_or_404(Expense, expense_id)

    if expense.status == "submitted":
        return jsonify({"error": "Submitted expenses cannot be edited."}), 400

    data = request.get_json(force=True)

    # Track manual overrides for audit (AC-9)
    overrides = expense.get_manual_overrides()
    editable_fields = {
        "vendor", "transaction_date", "amount", "tax_amount",
        "currency", "expense_type", "description", "job_id",
    }
    for field in editable_fields:
        if field in data:
            overrides[field] = data[field]
    expense.manual_overrides = json.dumps(overrides)

    expense = _apply_fields(expense, data)
    db.session.commit()
    return jsonify(expense.to_dict())


@expenses_bp.route("/<int:expense_id>/validate", methods=["POST"])
def validate_expense_route(expense_id):
    """
    AC-5 / AC-6 / AC-7: Run validation and return errors without submitting.
    """
    expense = db.get_or_404(Expense, expense_id)
    job = expense.job
    errors = validate_expense(expense, job)
    errors += check_duplicate_receipt(expense, db.session)
    return jsonify({"valid": len(errors) == 0, "errors": errors})


@expenses_bp.route("/<int:expense_id>/submit", methods=["POST"])
def submit_expense(expense_id):
    """
    AC-7 / AC-8: Validate and submit the expense.

    Prevents submission if any validation rule fails and returns clear errors.
    On success, sets status to 'submitted'.
    """
    expense = db.get_or_404(Expense, expense_id)

    if expense.status == "submitted":
        return jsonify({"error": "Expense is already submitted."}), 400

    job = expense.job
    errors = validate_expense(expense, job)
    errors += check_duplicate_receipt(expense, db.session)

    if errors:
        return jsonify(
            {
                "error": "Expense validation failed. Please fix the issues before submitting.",
                "errors": errors,
            }
        ), 422

    expense.status = "submitted"
    db.session.commit()
    return jsonify(
        {
            "message": "Expense submitted successfully.",
            "expense": expense.to_dict(),
        }
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _apply_fields(expense: Expense, data: dict) -> Expense:
    """Apply allowed fields from a request dict onto an Expense model instance."""
    if "job_id" in data:
        job_id = data["job_id"]
        if job_id is not None:
            job = db.session.get(Job, int(job_id))
            if job is None:
                raise ValueError(f"Job {job_id} not found.")
        expense.job_id = job_id

    if "vendor" in data:
        expense.vendor = data["vendor"]
    if "transaction_date" in data:
        raw = data["transaction_date"]
        expense.transaction_date = date.fromisoformat(raw) if raw else None
    if "amount" in data:
        expense.amount = float(data["amount"]) if data["amount"] is not None else None
    if "tax_amount" in data:
        expense.tax_amount = float(data["tax_amount"]) if data["tax_amount"] is not None else None
    if "currency" in data:
        expense.currency = data["currency"]
    if "expense_type" in data:
        expense.expense_type = data["expense_type"]
    if "description" in data:
        expense.description = data["description"]
    return expense
