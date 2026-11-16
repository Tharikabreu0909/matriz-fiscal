"""DEF-002: init_db / PRAGMA user_version (nunca rebaixa, não escreve em banco mais novo)."""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

import database
from services import backup_service


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "def002.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setattr(backup_service, "DB_PATH", path)
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw(path, sql, *args):
    con = sqlite3.connect(path)
    try:
        row = con.execute(sql, args).fetchall()
        con.commit()
        return row
    finally:
        con.close()


def _uv(path):
    return _raw(path, "PRAGMA user_version")[0][0]


def _legacy(path, version):
    """Banco com esquema atual e dados, carimbado com `version`."""
    database.init_db()
    database.create_company(cnpj="11.222.333/0001-81", legal_name="Legado Ltda")
    _raw(path, f"PRAGMA user_version = {version}")


def _newer(path, version, wal=False):
    """Banco de versão futura, com tabela desconhecida."""
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode = WAL")
    con.execute("CREATE TABLE futuro (x)")
    con.execute("INSERT INTO futuro VALUES (42)")
    con.execute(f"PRAGMA user_version = {version}")
    con.commit()
    con.close()


def _sidecars(path):
    return [p for p in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")) if p.exists()]


def test_new_database_missing_and_empty(db):
    database.init_db()
    assert _uv(db) == database.SCHEMA_VERSION
    db.unlink()
    for p in _sidecars(db):
        p.unlink()
    db.write_bytes(b"")
    database.init_db()
    assert _uv(db) == database.SCHEMA_VERSION


@pytest.mark.parametrize("version", [0, 1])
def test_legacy_is_migrated_keeping_data(db, version):
    _legacy(db, version)
    database.init_db()
    assert _uv(db) == 2
    assert [c["legal_name"] for c in database.list_companies()] == ["Legado Ltda"]


def test_current_is_idempotent_no_write(db):
    database.init_db()
    database.init_db()
    before = _sha(db)
    database.init_db()
    database.init_db()
    assert _sha(db) == before


@pytest.mark.parametrize("wal", [False, True])
@pytest.mark.parametrize("version", [3, 99])
def test_newer_is_rejected_without_any_write(db, version, wal):
    _newer(db, version, wal)
    before = _sha(db)
    with pytest.raises(database.DatabaseSchemaTooNewError):
        database.init_db()
    assert _sha(db) == before
    assert _sidecars(db) == []
    assert _uv(db) == version
    assert _raw(db, "SELECT x FROM futuro") == [(42,)]


def test_compatible_keeps_unknown_table(db):
    _legacy(db, 1)
    _raw(db, "CREATE TABLE extra (y)")
    _raw(db, "INSERT INTO extra VALUES (7)")
    database.init_db()
    assert _raw(db, "SELECT y FROM extra") == [(7,)]
    assert _uv(db) == 2


@pytest.mark.parametrize("version", [0, 1, 2])
def test_never_downgrades(db, version):
    _legacy(db, version)
    database.init_db()
    assert _uv(db) >= version


def _backup_with_version(db, version):
    database.init_db()
    database.create_company(cnpj="11.222.333/0001-81", legal_name="Atual Ltda")
    _raw(db, f"PRAGMA user_version = {version}")
    content = backup_service.create_backup("t").read_bytes()
    _raw(db, "PRAGMA user_version = 2")
    return content


def test_restore_rejects_newer_backup_and_keeps_db(db):
    content = _backup_with_version(db, 3)
    before = _sha(db)
    with pytest.raises(ValueError, match="mais recente"):
        backup_service.restore_backup(content, "t")
    # restore não deve ter alterado o banco (nem criado cópia de segurança)
    assert _uv(db) == 2
    assert [c["legal_name"] for c in database.list_companies()] == ["Atual Ltda"]


def test_restore_accepts_current_version_backup(db):
    content = _backup_with_version(db, 2)
    backup_service.restore_backup(content, "t")
    assert _uv(db) == 2
