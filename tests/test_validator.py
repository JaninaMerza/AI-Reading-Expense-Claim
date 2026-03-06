"""Tests for the expense validator service."""

import pytest
from datetime import date

from app.services.expense_validator import (
    validate_expense,
    check_duplicate_receipt,
    _validate_receipt_fields,
    _validate_job_rules,
)


# ---------------------------------------------------------------------------
# Minimal Expense and Job stubs for unit tests
# ---------------------------------------------------------------------------

class FakeExpense:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.vendor = kwargs.get("vendor", "Test Vendor")
        self.transaction_date = kwargs.get("transaction_date", date(2024, 6, 15))
        self.amount = kwargs.get("amount", 100.0)
        self.tax_amount = kwargs.get("tax_amount", 0.0)
        self.currency = kwargs.get("currency", "GBP")
        self.expense_type = kwargs.get("expense_type", "travel")
        self.receipt_hash = kwargs.get("receipt_hash", None)


class FakeJob:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Test Job")
        self.client = kwargs.get("client", "Test Client")
        self.start_date = kwargs.get("start_date", date(2024, 1, 1))
        self.end_date = kwargs.get("end_date", date(2025, 12, 31))
        self.is_active = kwargs.get("is_active", True)
        self.max_amount = kwargs.get("max_amount", None)
        self.currency = kwargs.get("currency", "GBP")
        _types = kwargs.get("allowed_expense_types", "travel,meals,accommodation,equipment,other")
        self._allowed_types = _types

    def get_allowed_types(self):
        return [t.strip().lower() for t in self._allowed_types.split(",") if t.strip()]


# ---------------------------------------------------------------------------
# Receipt field validation (AC-6)
# ---------------------------------------------------------------------------

class TestReceiptFieldValidation:
    def test_valid_expense_has_no_errors(self):
        expense = FakeExpense()
        errors = _validate_receipt_fields(expense)
        assert errors == []

    def test_missing_date(self):
        expense = FakeExpense(transaction_date=None)
        errors = _validate_receipt_fields(expense)
        assert any("date" in e.lower() for e in errors)

    def test_future_date(self):
        from datetime import timedelta
        future = date.today() + timedelta(days=10)
        expense = FakeExpense(transaction_date=future)
        errors = _validate_receipt_fields(expense)
        assert any("future" in e.lower() for e in errors)

    def test_missing_amount(self):
        expense = FakeExpense(amount=None)
        errors = _validate_receipt_fields(expense)
        assert any("amount" in e.lower() for e in errors)

    def test_zero_amount(self):
        expense = FakeExpense(amount=0.0)
        errors = _validate_receipt_fields(expense)
        assert any("greater than zero" in e.lower() for e in errors)

    def test_negative_amount(self):
        expense = FakeExpense(amount=-5.0)
        errors = _validate_receipt_fields(expense)
        assert any("greater than zero" in e.lower() for e in errors)

    def test_negative_tax(self):
        expense = FakeExpense(tax_amount=-1.0)
        errors = _validate_receipt_fields(expense)
        assert any("tax" in e.lower() for e in errors)

    def test_missing_vendor(self):
        expense = FakeExpense(vendor=None)
        errors = _validate_receipt_fields(expense)
        assert any("vendor" in e.lower() for e in errors)

    def test_empty_vendor(self):
        expense = FakeExpense(vendor="   ")
        errors = _validate_receipt_fields(expense)
        assert any("vendor" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Job rule validation (AC-5)
# ---------------------------------------------------------------------------

class TestJobRuleValidation:
    def test_valid_expense_job_pair(self):
        expense = FakeExpense()
        job = FakeJob()
        errors = _validate_job_rules(expense, job)
        assert errors == []

    def test_inactive_job(self):
        expense = FakeExpense()
        job = FakeJob(is_active=False)
        errors = _validate_job_rules(expense, job)
        assert any("not active" in e.lower() for e in errors)

    def test_date_before_job_start(self):
        expense = FakeExpense(transaction_date=date(2023, 12, 31))
        job = FakeJob(start_date=date(2024, 1, 1))
        errors = _validate_job_rules(expense, job)
        assert any("before" in e.lower() for e in errors)

    def test_date_after_job_end(self):
        expense = FakeExpense(transaction_date=date(2026, 1, 1))
        job = FakeJob(end_date=date(2025, 12, 31))
        errors = _validate_job_rules(expense, job)
        assert any("after" in e.lower() for e in errors)

    def test_disallowed_expense_type(self):
        expense = FakeExpense(expense_type="entertainment")
        job = FakeJob(allowed_expense_types="travel,meals")
        errors = _validate_job_rules(expense, job)
        assert any("not permitted" in e.lower() for e in errors)

    def test_allowed_expense_type(self):
        expense = FakeExpense(expense_type="travel")
        job = FakeJob(allowed_expense_types="travel,meals")
        errors = _validate_job_rules(expense, job)
        assert errors == []

    def test_exceeds_max_amount(self):
        expense = FakeExpense(amount=600.0)
        job = FakeJob(max_amount=500.0)
        errors = _validate_job_rules(expense, job)
        assert any("exceeds" in e.lower() for e in errors)

    def test_within_max_amount(self):
        expense = FakeExpense(amount=499.99)
        job = FakeJob(max_amount=500.0)
        errors = _validate_job_rules(expense, job)
        assert errors == []

    def test_no_amount_limit(self):
        expense = FakeExpense(amount=9999.0)
        job = FakeJob(max_amount=None)
        errors = _validate_job_rules(expense, job)
        assert errors == []


# ---------------------------------------------------------------------------
# Combined validate_expense
# ---------------------------------------------------------------------------

class TestValidateExpense:
    def test_valid_no_job(self):
        expense = FakeExpense()
        errors = validate_expense(expense, job=None)
        assert errors == []

    def test_valid_with_job(self):
        expense = FakeExpense()
        job = FakeJob()
        errors = validate_expense(expense, job)
        assert errors == []

    def test_accumulates_errors(self):
        expense = FakeExpense(amount=None, vendor=None)
        errors = validate_expense(expense, job=None)
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# Duplicate receipt check (AC-6)
# ---------------------------------------------------------------------------

class TestDuplicateReceiptCheck:
    def test_no_hash_returns_no_errors(self, db, draft_expense):
        """Expense with no receipt hash should not fail duplicate check."""
        draft_expense.receipt_hash = None
        db.session.commit()
        errors = check_duplicate_receipt(draft_expense, db.session)
        assert errors == []

    def test_unique_hash_passes(self, db, draft_expense):
        draft_expense.receipt_hash = "abc123unique"
        db.session.commit()
        errors = check_duplicate_receipt(draft_expense, db.session)
        assert errors == []

    def test_duplicate_hash_fails(self, db, draft_expense, sample_job):
        from app.models import Expense
        from datetime import date

        # Create a second expense with the same hash
        second = Expense(
            job_id=sample_job.id,
            vendor="Other",
            transaction_date=date(2024, 7, 1),
            amount=50.0,
            currency="GBP",
            expense_type="meals",
            status="draft",
            receipt_hash="duplicate_hash_xyz",
        )
        db.session.add(second)
        draft_expense.receipt_hash = "duplicate_hash_xyz"
        db.session.commit()

        errors = check_duplicate_receipt(draft_expense, db.session)
        assert len(errors) == 1
        assert "already been submitted" in errors[0].lower()
