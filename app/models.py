import hashlib
import json
from datetime import datetime, timezone

from app import db


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    client = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Comma-separated list of allowed expense types, e.g. "travel,meals,accommodation"
    allowed_expense_types = db.Column(db.Text, nullable=False, default="travel,meals,accommodation,equipment,other")
    max_amount = db.Column(db.Float, nullable=True)  # None means no limit
    currency = db.Column(db.String(10), nullable=False, default="GBP")

    expenses = db.relationship("Expense", back_populates="job", lazy="dynamic")

    def get_allowed_types(self):
        return [t.strip().lower() for t in self.allowed_expense_types.split(",") if t.strip()]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "client": self.client,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "allowed_expense_types": self.get_allowed_types(),
            "max_amount": self.max_amount,
            "currency": self.currency,
        }


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=True)
    vendor = db.Column(db.String(200), nullable=True)
    transaction_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Float, nullable=True)
    tax_amount = db.Column(db.Float, nullable=True, default=0.0)
    currency = db.Column(db.String(10), nullable=False, default="GBP")
    expense_type = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft")
    # Receipt file info
    receipt_filename = db.Column(db.String(255), nullable=True)
    receipt_path = db.Column(db.String(500), nullable=True)
    receipt_hash = db.Column(db.String(64), nullable=True)
    # JSON fields for AI data and audit trail
    extracted_data = db.Column(db.Text, nullable=True)   # JSON from OCR
    manual_overrides = db.Column(db.Text, nullable=True) # JSON of user edits
    # Flags from extraction
    extraction_flags = db.Column(db.Text, nullable=True) # JSON list of flagged fields
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    job = db.relationship("Job", back_populates="expenses")

    def get_extracted_data(self):
        return json.loads(self.extracted_data) if self.extracted_data else {}

    def get_manual_overrides(self):
        return json.loads(self.manual_overrides) if self.manual_overrides else {}

    def get_extraction_flags(self):
        return json.loads(self.extraction_flags) if self.extraction_flags else []

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job": self.job.to_dict() if self.job else None,
            "vendor": self.vendor,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "amount": self.amount,
            "tax_amount": self.tax_amount,
            "currency": self.currency,
            "expense_type": self.expense_type,
            "description": self.description,
            "status": self.status,
            "receipt_filename": self.receipt_filename,
            "extracted_data": self.get_extracted_data(),
            "manual_overrides": self.get_manual_overrides(),
            "extraction_flags": self.get_extraction_flags(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def compute_file_hash(filepath):
        """Compute SHA-256 hash of a file for duplicate detection."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
