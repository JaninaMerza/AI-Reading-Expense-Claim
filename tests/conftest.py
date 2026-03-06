"""Shared test fixtures."""

import os
import pytest

from app import create_app, db as _db
from config import TestingConfig


@pytest.fixture(scope="session")
def app():
    """Create a Flask test application with an in-memory SQLite DB."""
    os.makedirs(TestingConfig.UPLOAD_FOLDER, exist_ok=True)
    application = create_app(TestingConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    """Provide a clean DB session per test function."""
    with app.app_context():
        yield _db
        _db.session.rollback()
        # Truncate all tables
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture()
def sample_job(db):
    from app.models import Job
    from datetime import date

    job = Job(
        name="Test Project Alpha",
        client="Acme Corp",
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        is_active=True,
        allowed_expense_types="travel,meals,accommodation,equipment,other",
        max_amount=500.0,
        currency="GBP",
    )
    db.session.add(job)
    db.session.commit()
    return job


@pytest.fixture()
def draft_expense(db, sample_job):
    from app.models import Expense
    from datetime import date

    expense = Expense(
        job_id=sample_job.id,
        vendor="Test Vendor",
        transaction_date=date(2024, 6, 15),
        amount=120.0,
        tax_amount=20.0,
        currency="GBP",
        expense_type="travel",
        status="draft",
    )
    db.session.add(expense)
    db.session.commit()
    return expense
