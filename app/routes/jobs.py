"""Jobs API routes."""

from flask import Blueprint, jsonify, request
from datetime import date

from app import db
from app.models import Job

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/", methods=["GET"])
def list_jobs():
    active_only = request.args.get("active_only", "false").lower() == "true"
    query = Job.query
    if active_only:
        query = query.filter_by(is_active=True)
    jobs = query.order_by(Job.name).all()
    return jsonify([j.to_dict() for j in jobs])


@jobs_bp.route("/<int:job_id>", methods=["GET"])
def get_job(job_id):
    job = db.get_or_404(Job, job_id)
    return jsonify(job.to_dict())


@jobs_bp.route("/", methods=["POST"])
def create_job():
    data = request.get_json(force=True)
    required = ["name", "client", "start_date", "end_date"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])
    except ValueError as exc:
        return jsonify({"error": f"Invalid date format: {exc}"}), 400

    if end < start:
        return jsonify({"error": "end_date must be on or after start_date"}), 400

    job = Job(
        name=data["name"],
        client=data["client"],
        start_date=start,
        end_date=end,
        is_active=data.get("is_active", True),
        allowed_expense_types=data.get(
            "allowed_expense_types", "travel,meals,accommodation,equipment,other"
        ),
        max_amount=data.get("max_amount"),
        currency=data.get("currency", "GBP"),
    )
    db.session.add(job)
    db.session.commit()
    return jsonify(job.to_dict()), 201


@jobs_bp.route("/<int:job_id>", methods=["PUT"])
def update_job(job_id):
    job = db.get_or_404(Job, job_id)
    data = request.get_json(force=True)

    if "name" in data:
        job.name = data["name"]
    if "client" in data:
        job.client = data["client"]
    if "start_date" in data:
        try:
            job.start_date = date.fromisoformat(data["start_date"])
        except ValueError as exc:
            return jsonify({"error": f"Invalid start_date: {exc}"}), 400
    if "end_date" in data:
        try:
            job.end_date = date.fromisoformat(data["end_date"])
        except ValueError as exc:
            return jsonify({"error": f"Invalid end_date: {exc}"}), 400
    if "is_active" in data:
        job.is_active = bool(data["is_active"])
    if "allowed_expense_types" in data:
        job.allowed_expense_types = data["allowed_expense_types"]
    if "max_amount" in data:
        job.max_amount = data["max_amount"]
    if "currency" in data:
        job.currency = data["currency"]

    db.session.commit()
    return jsonify(job.to_dict())
