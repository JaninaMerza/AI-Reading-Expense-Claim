"""Integration tests for the Expenses API."""

import pytest
from datetime import date


class TestListExpenses:
    def test_empty_list(self, client, db):
        res = client.get("/api/expenses/")
        assert res.status_code == 200
        assert res.get_json() == []

    def test_filter_by_status(self, client, db, draft_expense):
        res = client.get("/api/expenses/?status=draft")
        data = res.get_json()
        assert all(e["status"] == "draft" for e in data)

    def test_filter_by_job(self, client, db, draft_expense, sample_job):
        res = client.get(f"/api/expenses/?job_id={sample_job.id}")
        data = res.get_json()
        assert all(e["job_id"] == sample_job.id for e in data)


class TestCreateExpense:
    def test_create_minimal_expense(self, client, db):
        res = client.post("/api/expenses/", json={})
        assert res.status_code == 201
        assert res.get_json()["status"] == "draft"

    def test_create_with_fields(self, client, db, sample_job):
        payload = {
            "job_id": sample_job.id,
            "vendor": "Vendor Co",
            "transaction_date": "2024-06-01",
            "amount": 75.0,
            "currency": "GBP",
            "expense_type": "travel",
        }
        res = client.post("/api/expenses/", json=payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["vendor"] == "Vendor Co"
        assert data["amount"] == 75.0


class TestGetExpense:
    def test_get_existing(self, client, db, draft_expense):
        res = client.get(f"/api/expenses/{draft_expense.id}")
        assert res.status_code == 200
        assert res.get_json()["id"] == draft_expense.id

    def test_get_nonexistent(self, client, db):
        res = client.get("/api/expenses/9999")
        assert res.status_code == 404


class TestUpdateExpense:
    def test_update_vendor(self, client, db, draft_expense):
        res = client.put(f"/api/expenses/{draft_expense.id}", json={"vendor": "Updated Vendor"})
        assert res.status_code == 200
        assert res.get_json()["vendor"] == "Updated Vendor"

    def test_manual_override_recorded(self, client, db, draft_expense):
        client.put(f"/api/expenses/{draft_expense.id}", json={"vendor": "Manual Vendor"})
        res = client.get(f"/api/expenses/{draft_expense.id}")
        overrides = res.get_json()["manual_overrides"]
        assert overrides.get("vendor") == "Manual Vendor"

    def test_cannot_edit_submitted(self, client, db, draft_expense):
        draft_expense.status = "submitted"
        from app import db as _db
        _db.session.commit()
        res = client.put(f"/api/expenses/{draft_expense.id}", json={"vendor": "X"})
        assert res.status_code == 400


class TestValidateExpenseRoute:
    def test_valid_expense(self, client, db, draft_expense):
        res = client.post(f"/api/expenses/{draft_expense.id}/validate")
        assert res.status_code == 200
        data = res.get_json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_expense_missing_amount(self, client, db, sample_job):
        from app.models import Expense
        expense = Expense(
            job_id=sample_job.id,
            vendor="X",
            transaction_date=date(2024, 6, 1),
            amount=None,
            currency="GBP",
            expense_type="travel",
        )
        from app import db as _db
        _db.session.add(expense)
        _db.session.commit()
        res = client.post(f"/api/expenses/{expense.id}/validate")
        data = res.get_json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


class TestSubmitExpense:
    def test_submit_valid_expense(self, client, db, draft_expense):
        res = client.post(f"/api/expenses/{draft_expense.id}/submit")
        assert res.status_code == 200
        data = res.get_json()
        assert data["expense"]["status"] == "submitted"
        assert "message" in data

    def test_cannot_resubmit(self, client, db, draft_expense):
        client.post(f"/api/expenses/{draft_expense.id}/submit")
        res = client.post(f"/api/expenses/{draft_expense.id}/submit")
        assert res.status_code == 400

    def test_submit_invalid_expense_returns_422(self, client, db, sample_job):
        from app.models import Expense
        expense = Expense(
            job_id=sample_job.id,
            transaction_date=date(2024, 6, 1),
            amount=None,      # missing – should fail validation
            currency="GBP",
            expense_type="travel",
        )
        from app import db as _db
        _db.session.add(expense)
        _db.session.commit()
        res = client.post(f"/api/expenses/{expense.id}/submit")
        assert res.status_code == 422
        data = res.get_json()
        assert "errors" in data

    def test_submit_inactive_job_blocked(self, client, db, sample_job):
        from app.models import Expense
        from datetime import date
        sample_job.is_active = False
        from app import db as _db
        _db.session.commit()
        expense = Expense(
            job_id=sample_job.id,
            vendor="V",
            transaction_date=date(2024, 6, 1),
            amount=50.0,
            currency="GBP",
            expense_type="travel",
        )
        _db.session.add(expense)
        _db.session.commit()
        res = client.post(f"/api/expenses/{expense.id}/submit")
        assert res.status_code == 422
