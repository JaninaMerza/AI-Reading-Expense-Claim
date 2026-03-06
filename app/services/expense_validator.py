"""
Expense validation service.

Validates an expense record against job rules and receipt integrity checks
before allowing submission.
"""

from datetime import date


def validate_expense(expense, job=None) -> list[str]:
    """
    Run all validation rules on an expense.

    Returns a list of error messages. An empty list means the expense is valid.
    """
    errors = []
    errors.extend(_validate_receipt_fields(expense))
    if job is not None:
        errors.extend(_validate_job_rules(expense, job))
    return errors


# ---------------------------------------------------------------------------
# Rule groups
# ---------------------------------------------------------------------------

def _validate_receipt_fields(expense) -> list[str]:
    """AC-6: Receipt validity checks."""
    errors = []

    # Receipt date present and valid
    if expense.transaction_date is None:
        errors.append("Receipt date is missing. Please enter the transaction date.")
    elif expense.transaction_date > date.today():
        errors.append("Transaction date cannot be in the future.")

    # Amount > 0
    if expense.amount is None:
        errors.append("Receipt amount is missing. Please enter the expense amount.")
    elif expense.amount <= 0:
        errors.append("Receipt amount must be greater than zero.")

    # Tax amount non-negative (if provided)
    if expense.tax_amount is not None and expense.tax_amount < 0:
        errors.append("Tax amount cannot be negative.")

    # Vendor present
    if not expense.vendor or not expense.vendor.strip():
        errors.append("Vendor / merchant name is missing.")

    return errors


def _validate_job_rules(expense, job) -> list[str]:
    """AC-4 & AC-5: Job association and validation rules."""
    errors = []

    # Job must be active
    if not job.is_active:
        errors.append(f"Job '{job.name}' is not active and cannot accept new expenses.")

    # Expense date within job date range
    if expense.transaction_date:
        if expense.transaction_date < job.start_date:
            errors.append(
                f"Transaction date {expense.transaction_date} is before the job start date {job.start_date}."
            )
        if expense.transaction_date > job.end_date:
            errors.append(
                f"Transaction date {expense.transaction_date} is after the job end date {job.end_date}."
            )

    # Expense type permitted for job
    if expense.expense_type:
        allowed = job.get_allowed_types()
        if allowed and expense.expense_type.lower() not in allowed:
            errors.append(
                f"Expense type '{expense.expense_type}' is not permitted for job '{job.name}'. "
                f"Allowed types: {', '.join(allowed)}."
            )

    # Amount within job limit
    if job.max_amount is not None and expense.amount is not None:
        if expense.amount > job.max_amount:
            errors.append(
                f"Expense amount {expense.currency} {expense.amount:.2f} exceeds "
                f"the job limit of {expense.currency} {job.max_amount:.2f}."
            )

    return errors


def check_duplicate_receipt(expense, session) -> list[str]:
    """
    AC-6: Verify the receipt file hash is not already attached to another expense.
    Returns a list with an error string if duplicate found, else empty list.
    """
    from app.models import Expense

    if not expense.receipt_hash:
        return []

    duplicate = (
        session.query(Expense)
        .filter(
            Expense.receipt_hash == expense.receipt_hash,
            Expense.id != expense.id,
        )
        .first()
    )
    if duplicate:
        return [
            f"This receipt has already been submitted on expense #{duplicate.id}. "
            "Each receipt can only be used once."
        ]
    return []
