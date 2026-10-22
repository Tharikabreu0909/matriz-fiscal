from __future__ import annotations

import os

import database
from fastapi.testclient import TestClient


def test_delete_company_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "api-delete.db")
    database.init_db()

    import app

    client = TestClient(app.app)
    created = client.post(
        "/api/companies",
        json={
            "cnpj": "10689433000150",
            "legal_name": "Empresa API",
            "trade_name": "",
            "state_registration": "",
            "city": "",
            "state": "",
            "default_annex": "I",
            "notes": "",
        },
    )
    assert created.status_code == 201
    company_id = created.json()["company"]["id"]

    deleted = client.delete(f"/api/companies/{company_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "DELETED"

    missing = client.get(f"/api/companies/{company_id}")
    assert missing.status_code == 404
