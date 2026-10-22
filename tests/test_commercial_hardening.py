from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
import pytest

import app
import database
from services import backup_service, file_storage
from services.security import is_valid_cnpj, validate_malha_identity


ACONCHEGO_MALHA = Path("/mnt/data/malha fiscal aconchego(3).pdf")


def configure_isolated_runtime(tmp_path, monkeypatch):
    db_path = tmp_path / "checkfiscal.db"
    documents = tmp_path / "documents"
    backups = tmp_path / "backups"
    documents.mkdir()
    backups.mkdir()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(file_storage, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(backup_service, "DB_PATH", db_path)
    monkeypatch.setattr(backup_service, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(backup_service, "BACKUPS_DIR", backups)
    database.init_db()
    return db_path, documents, backups


def test_cnpj_checksum_validation():
    assert is_valid_cnpj("41.973.739/0001-67")
    assert is_valid_cnpj("09.462.429/0001-75")
    assert not is_valid_cnpj("12.345.678/0001-90")
    assert not is_valid_cnpj("00.000.000/0000-00")


def test_malha_identity_prefers_cfdf_match():
    company = {
        "legal_name": "ACONCHEGO DA MODA COMERCIO DE ROUPAS LTDA",
        "trade_name": "ACONCHEGO DA MODA",
        "state_registration": "08.055.883/001-11",
    }
    malha = {
        "contributor": {
            "legal_name": "ACONCHEGO DA MODA COMERCIO DE ROUPAS LTDA",
            "cfdf": "08.055.883/001-11",
        }
    }
    result = validate_malha_identity(company, malha)
    assert result["match"] is True
    assert result["status"] == "MATCH_BY_REGISTRATION"


def test_wrong_company_blocks_malha_and_override_is_audited(tmp_path, monkeypatch):
    _, documents, _ = configure_isolated_runtime(tmp_path, monkeypatch)
    client = TestClient(app.app)

    created = client.post(
        "/api/companies",
        json={
            "cnpj": "09.462.429/0001-75",
            "legal_name": "C E M CONFECCOES E COMERCIO DE ROUPAS LTDA ME",
            "trade_name": "C E M CONFECCOES",
            "state_registration": "07.501.445/001-33",
            "city": "Brasília",
            "state": "DF",
            "default_annex": "I",
            "notes": "",
        },
    )
    assert created.status_code == 201
    company_id = created.json()["company"]["id"]

    with ACONCHEGO_MALHA.open("rb") as handle:
        blocked = client.post(
            f"/api/analyze-malha?company_id={company_id}",
            files={"file": (ACONCHEGO_MALHA.name, handle, "application/pdf")},
        )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "MALHA_IDENTITY_MISMATCH"

    with ACONCHEGO_MALHA.open("rb") as handle:
        accepted = client.post(
            f"/api/analyze-malha?company_id={company_id}&confirm_identity_mismatch=true",
            files={"file": (ACONCHEGO_MALHA.name, handle, "application/pdf")},
        )
    assert accepted.status_code == 200
    process_id = accepted.json()["process_id"]

    events = database.list_process_events(process_id)
    assert events[0]["details"]["identity_override"] is True
    stored = database.list_stored_documents(process_id)
    assert len(stored) == 1
    assert (documents / stored[0]["stored_path"]).exists()


def test_matching_malha_is_stored_and_can_be_downloaded(tmp_path, monkeypatch):
    _, _, _ = configure_isolated_runtime(tmp_path, monkeypatch)
    client = TestClient(app.app)

    created = client.post(
        "/api/companies",
        json={
            "cnpj": "41.973.739/0001-67",
            "legal_name": "ACONCHEGO DA MODA COMERCIO DE ROUPAS LTDA",
            "trade_name": "ACONCHEGO DA MODA",
            "state_registration": "08.055.883/001-11",
            "city": "Brasília",
            "state": "DF",
            "default_annex": "I",
            "notes": "",
        },
    )
    company_id = created.json()["company"]["id"]

    with ACONCHEGO_MALHA.open("rb") as handle:
        response = client.post(
            f"/api/analyze-malha?company_id={company_id}",
            files={"file": (ACONCHEGO_MALHA.name, handle, "application/pdf")},
        )
    assert response.status_code == 200
    assert response.json()["identity_validation"]["match"] is True
    process_id = response.json()["process_id"]

    listed = client.get(f"/api/process/{process_id}/documents")
    assert listed.status_code == 200
    document = listed.json()["documents"][0]
    downloaded = client.get(document["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content == ACONCHEGO_MALHA.read_bytes()


def test_backup_and_restore_preserve_database_and_documents(tmp_path, monkeypatch):
    _, documents, _ = configure_isolated_runtime(tmp_path, monkeypatch)
    company_id = database.create_company(
        "41.973.739/0001-67",
        "Empresa protegida",
    )
    process_id = database.create_process(
        {
            "contributor": {"legal_name": "Empresa protegida", "cfdf": ""},
            "source_document": {"file_name": "malha.pdf"},
            "work_months": [],
            "raw_rows": [],
        },
        {"required_pgdas": [], "summary": {}},
        "41973739000167",
        company_id=company_id,
    )
    folder = documents / f"company-{company_id}" / f"process-{process_id}"
    folder.mkdir(parents=True)
    original = folder / "malha-test.pdf"
    original.write_bytes(b"PDF TEST")

    backup = backup_service.create_backup("1.39.0")
    assert backup.exists()
    with zipfile.ZipFile(backup) as archive:
        assert "manifest.json" in archive.namelist()
        assert "database/checkfiscal.db" in archive.namelist()
        assert any(name.startswith("documents/") for name in archive.namelist())

    database.delete_company(company_id)
    original.unlink()
    result = backup_service.restore_backup(backup.read_bytes(), "1.39.0")
    assert result["restart_required"] is True
    assert database.get_company(company_id)["legal_name"] == "Empresa protegida"
    assert original.exists()


def test_explicit_schema_migration_is_recorded(tmp_path, monkeypatch):
    configure_isolated_runtime(tmp_path, monkeypatch)
    with database.connect() as connection:
        migrations = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert [row["version"] for row in migrations] == [1]
    assert user_version == 2
