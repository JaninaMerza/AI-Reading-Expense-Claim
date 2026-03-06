"""Integration tests for the Jobs API."""

import pytest


class TestListJobs:
    def test_empty_list(self, client, db):
        res = client.get("/api/jobs/")
        assert res.status_code == 200
        assert res.get_json() == []

    def test_returns_created_jobs(self, client, db, sample_job):
        res = client.get("/api/jobs/")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Project Alpha"

    def test_active_only_filter(self, client, db, sample_job):
        from app.models import Job
        from datetime import date
        inactive = Job(
            name="Old Job", client="Foo", start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31), is_active=False,
        )
        db.session.add(inactive)
        db.session.commit()
        res = client.get("/api/jobs/?active_only=true")
        jobs = res.get_json()
        assert all(j["is_active"] for j in jobs)


class TestCreateJob:
    def test_create_valid_job(self, client, db):
        payload = {
            "name": "New Job",
            "client": "Client X",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        res = client.post("/api/jobs/", json=payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["name"] == "New Job"
        assert data["is_active"] is True

    def test_missing_required_field(self, client, db):
        res = client.post("/api/jobs/", json={"name": "Incomplete"})
        assert res.status_code == 400
        assert "error" in res.get_json()

    def test_invalid_date_format(self, client, db):
        payload = {
            "name": "Job", "client": "C",
            "start_date": "not-a-date", "end_date": "2024-12-31",
        }
        res = client.post("/api/jobs/", json=payload)
        assert res.status_code == 400

    def test_end_before_start(self, client, db):
        payload = {
            "name": "Job", "client": "C",
            "start_date": "2024-12-31", "end_date": "2024-01-01",
        }
        res = client.post("/api/jobs/", json=payload)
        assert res.status_code == 400


class TestGetJob:
    def test_get_existing(self, client, db, sample_job):
        res = client.get(f"/api/jobs/{sample_job.id}")
        assert res.status_code == 200
        assert res.get_json()["id"] == sample_job.id

    def test_get_nonexistent(self, client, db):
        res = client.get("/api/jobs/999")
        assert res.status_code == 404


class TestUpdateJob:
    def test_update_name(self, client, db, sample_job):
        res = client.put(f"/api/jobs/{sample_job.id}", json={"name": "Renamed Job"})
        assert res.status_code == 200
        assert res.get_json()["name"] == "Renamed Job"

    def test_deactivate_job(self, client, db, sample_job):
        res = client.put(f"/api/jobs/{sample_job.id}", json={"is_active": False})
        assert res.status_code == 200
        assert res.get_json()["is_active"] is False
