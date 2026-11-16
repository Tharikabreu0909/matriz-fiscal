"""T03: ciclo de vida das conexões (DEF-001) e restauração segura."""
from __future__ import annotations

import sqlite3
import threading

import pytest

import database
from services import backup_service


def _cnpj_company(name="Empresa T03 Ltda"):
    return database.create_company(cnpj="11.222.333/0001-81", legal_name=name)


def test_connect_closes_after_success_and_commits():
    with database.connect() as connection:
        connection.execute("CREATE TABLE t03 (x)")
        connection.execute("INSERT INTO t03 VALUES (1)")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with database.connect() as other:
        assert other.execute("SELECT x FROM t03").fetchone()[0] == 1


def test_connect_closes_and_rolls_back_on_exception():
    with database.connect() as connection:
        connection.execute("CREATE TABLE t03 (x)")
    with pytest.raises(RuntimeError):
        with database.connect() as connection:
            connection.execute("INSERT INTO t03 VALUES (1)")
            raise RuntimeError("falha")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with database.connect() as other:
        assert other.execute("SELECT COUNT(*) FROM t03").fetchone()[0] == 0
    assert database._open_connections == 0


def test_restore_succeeds_without_gc_and_keeps_data():
    company_id = _cnpj_company()
    backup = backup_service.create_backup("t03")
    backup_service.restore_backup(backup.read_bytes(), "t03")
    assert database.get_company(company_id)["legal_name"] == "Empresa T03 Ltda"
    with database.connect() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_restore_invalid_backup_preserves_database():
    company_id = _cnpj_company()
    with pytest.raises(Exception):
        backup_service.restore_backup(b"nao e um zip", "t03")
    assert database.get_company(company_id)["legal_name"] == "Empresa T03 Ltda"


def test_restore_corrupt_database_in_valid_zip_preserves_database(tmp_path):
    import json
    import zipfile

    company_id = _cnpj_company()
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"product": "CheckFiscal", "format_version": 1}),
        )
        archive.writestr("database/checkfiscal.db", b"X" * 4096)
    with pytest.raises(Exception):
        backup_service.restore_backup(bad.read_bytes(), "t03")
    assert database.get_company(company_id)["legal_name"] == "Empresa T03 Ltda"


def test_concurrent_restore_is_rejected():
    with database.exclusive_access():
        with pytest.raises(database.DatabaseBusyError):
            backup_service.restore_backup(
                backup_service.create_backup("t03").read_bytes(), "t03"
            )


def test_restore_waits_for_open_connection_then_fails_controlled():
    company_id = _cnpj_company()
    content = backup_service.create_backup("t03").read_bytes()
    started = threading.Event()
    release = threading.Event()

    def hold():
        with database.connect():
            started.set()
            release.wait(10)

    thread = threading.Thread(target=hold)
    thread.start()
    started.wait(5)
    try:
        with pytest.raises(database.DatabaseBusyError):
            with database.exclusive_access(timeout=0.2):
                pass
    finally:
        release.set()
        thread.join()
    backup_service.restore_backup(content, "t03")
    assert database.get_company(company_id) is not None
