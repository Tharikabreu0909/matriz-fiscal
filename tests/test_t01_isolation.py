"""Testes canário do isolamento da suíte (Fase 0, T01).

Estes testes não verificam regra fiscal. Eles provam que a suíte não
consegue ler nem alterar os dados reais do operador.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_canary_all_persistence_paths_are_inside_test_root(isolation_guard):
    import app  # noqa: F401  carrega todos os módulos que guardam caminhos
    import database  # noqa: F401
    import services.backup_service  # noqa: F401
    import services.support_bundle  # noqa: F401

    paths = isolation_guard.persistence_paths()

    assert len(paths) >= 15
    assert isolation_guard.problems() == []
    for path in paths.values():
        assert isolation_guard.test_root in Path(path).resolve().parents


def test_canary_environment_points_to_test_root(isolation_guard):
    root = isolation_guard.test_root
    for variable in ("CHECKFISCAL_DATA_DIR", "CHECKFISCAL_DB_PATH", "LOCALAPPDATA", "APPDATA"):
        assert root in Path(os.environ[variable]).resolve().parents


def test_canary_real_data_locations_are_protected(isolation_guard):
    roots = {Path(root).name.lower() for root in isolation_guard.protected_roots}
    assert "checkfiscal" in roots  # %LOCALAPPDATA%\CheckFiscal
    assert "checkfiscal_data" in roots  # volume do Docker
    assert "checkfiscal_local.db" in roots  # banco legado


def test_canary_primary_checkout_data_is_protected_from_a_worktree(isolation_guard):
    # Docker monta o checkout principal; num worktree, REPO_ROOT é outro caminho.
    marker = REPO_ROOT / ".git"
    if not marker.is_file():
        pytest.skip("não é um worktree git")
    gitdir = Path(marker.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
    primary = next(p.parent for p in gitdir.parents if p.name == ".git")
    protected = {os.path.normcase(os.path.abspath(r)) for r in isolation_guard.protected_roots}
    assert os.path.normcase(os.path.abspath(primary / "checkfiscal_data")) in protected


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_real_sqlite_files_cannot_be_opened(isolation_guard, suffix):
    for root in isolation_guard.protected_roots:
        if not root.lower().endswith("checkfiscal"):
            continue
        target = Path(root) / f"checkfiscal.db{suffix}"
        for mode in ("rb", "r+b", "ab", "wb"):
            with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
                open(target, mode)


def test_real_database_cannot_be_connected(isolation_guard):
    for root in isolation_guard.protected_roots:
        target = Path(root) / "checkfiscal.db"
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            sqlite3.connect(target)
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True)


def test_real_directories_cannot_be_listed_copied_or_removed(isolation_guard, tmp_path):
    for root in isolation_guard.protected_roots:
        base = Path(root)
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            os.listdir(base)
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            shutil.rmtree(base / "documents")
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            os.remove(base / "checkfiscal.db")
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            os.replace(tmp_path / "x.db", base / "checkfiscal.db")
        with isolation_guard.expect_blocked(), pytest.raises(PermissionError):
            shutil.copyfile(base / "checkfiscal.db", tmp_path / "copy.db")


def test_application_writes_only_to_test_database(isolation_guard):
    import database

    company_id = database.create_company(
        cnpj="11.222.333/0001-81",
        legal_name="Empresa Canário Ltda",
    )

    assert database.get_company(company_id)["legal_name"] == "Empresa Canário Ltda"
    assert isolation_guard.test_root in Path(database.DB_PATH).resolve().parents


def test_database_is_recreated_for_each_test():
    import database

    # O teste anterior criou uma empresa; aqui o banco deve estar vazio.
    assert database.list_companies() == []


def test_backup_and_restore_services_target_test_root(isolation_guard):
    from services import backup_service

    backup = backup_service.create_backup("teste-isolamento")
    assert isolation_guard.test_root in backup.resolve().parents

    result = backup_service.restore_backup(backup.read_bytes(), "teste-isolamento")
    assert isolation_guard.test_root in Path(result["safety_backup"]).resolve().parents
    assert isolation_guard.test_root in backup_service.DB_PATH.resolve().parents


def test_external_network_is_blocked(isolation_guard):
    from services.legal_charges import LegalChargesError, fetch_bcb_monthly_selic
    from datetime import date

    with pytest.raises(OSError):
        socket.getaddrinfo("api.bcb.gov.br", 443)
    with pytest.raises(OSError):
        socket.create_connection(("8.8.8.8", 53), timeout=1)
    with pytest.raises(LegalChargesError):
        fetch_bcb_monthly_selic(date(2025, 1, 1), date(2025, 3, 31), timeout_seconds=1)
    assert any(item["target"] == "api.bcb.gov.br" for item in isolation_guard.network_blocked)


def test_loopback_network_remains_available():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=1)
        client.close()
    finally:
        server.close()


def test_subprocess_is_blocked_without_marker():
    with pytest.raises(PermissionError):
        subprocess.run([sys.executable, "-c", "pass"], check=False)


@pytest.mark.allow_subprocess(
    reason="Prova que um processo separado, que herda o ambiente do teste, "
    "resolve os caminhos de persistência no diretório temporário."
)
def test_separate_process_resolves_paths_inside_test_root(isolation_guard):
    script = (
        "import json, services.runtime_paths as r, database, services.backup_service as b;"
        "print(json.dumps({'data': str(r.DATA_DIR), 'db': str(database.DB_PATH),"
        "'docs': str(r.DOCUMENTS_DIR), 'backups': str(b.BACKUPS_DIR)}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    paths = json.loads(completed.stdout.strip().splitlines()[-1])

    for path in paths.values():
        assert isolation_guard.test_root in Path(path).resolve().parents


def test_no_violation_recorded_so_far(isolation_guard):
    assert isolation_guard.violations == []
