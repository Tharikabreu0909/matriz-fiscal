from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json
import os
import shutil
import sqlite3
import zipfile

from database import exclusive_access
from services.runtime_paths import BACKUPS_DIR, DB_PATH, DOCUMENTS_DIR


BACKUP_FORMAT_VERSION = 1
MAX_BACKUP_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_BACKUP_MEMBERS = 20_000


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def create_backup(app_version: str) -> Path:
    backup_path = BACKUPS_DIR / f"checkfiscal-backup-{_timestamp()}.zip"

    with TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        database_copy = temp / "checkfiscal.db"

        source = sqlite3.connect(DB_PATH)
        try:
            source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            destination = sqlite3.connect(database_copy)
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()

        manifest = {
            "product": "CheckFiscal",
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": app_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (temp / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "database/checkfiscal.db")
            archive.write(temp / "manifest.json", "manifest.json")
            if DOCUMENTS_DIR.exists():
                for file in DOCUMENTS_DIR.rglob("*"):
                    if file.is_file():
                        archive.write(
                            file,
                            Path("documents") / file.relative_to(DOCUMENTS_DIR),
                        )

    return backup_path


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        candidate = (destination / member.filename).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("O backup contém caminhos inválidos.")
    archive.extractall(destination)


def validate_backup_bytes(content: bytes) -> dict[str, Any]:
    with TemporaryDirectory() as temp_name:
        archive_path = Path(temp_name) / "backup.zip"
        archive_path.write_bytes(content)
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_BACKUP_MEMBERS:
                raise ValueError("O backup possui arquivos demais.")
            total_size = sum(member.file_size for member in members)
            if total_size > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise ValueError("O backup ultrapassa o limite de segurança.")
            names = {member.filename for member in members}
            if "manifest.json" not in names or "database/checkfiscal.db" not in names:
                raise ValueError("O arquivo não é um backup válido do Matriz Fiscal.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("product") != "CheckFiscal":
                raise ValueError("Backup de outro produto.")
            if int(manifest.get("format_version", 0)) != BACKUP_FORMAT_VERSION:
                raise ValueError("Versão de backup não suportada.")
            return manifest


def _integrity_ok(path: Path) -> bool:
    check = sqlite3.connect(path)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()
        return bool(result) and result[0] == "ok"
    finally:
        check.close()


def restore_backup(content: bytes, app_version: str) -> dict[str, Any]:
    manifest = validate_backup_bytes(content)  # antes de tocar no banco

    with TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        archive_path = temp / "backup.zip"
        archive_path.write_bytes(content)
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, temp / "extracted")
        extracted = temp / "extracted"
        restored_db = extracted / "database" / "checkfiscal.db"
        if not _integrity_ok(restored_db):
            raise ValueError("O banco do backup não passou na verificação de integridade.")

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_access():  # sem conexões abertas: seguro mexer em -wal/-shm
            safety_backup = create_backup(app_version)
            previous_db = temp / "previous.db"
            had_db = DB_PATH.exists()
            if had_db:
                shutil.copy2(DB_PATH, previous_db)  # create_backup já fez checkpoint
            staged_docs = DOCUMENTS_DIR.with_name(DOCUMENTS_DIR.name + ".new")
            old_docs = DOCUMENTS_DIR.with_name(DOCUMENTS_DIR.name + ".old")
            shutil.rmtree(staged_docs, ignore_errors=True)
            shutil.rmtree(old_docs, ignore_errors=True)
            restored_documents = extracted / "documents"
            if restored_documents.exists():
                shutil.copytree(restored_documents, staged_docs)
            else:
                staged_docs.mkdir(parents=True)
            temporary_db = DB_PATH.with_suffix(".restore.tmp")
            try:
                shutil.copy2(restored_db, temporary_db)
                for suffix in ("-wal", "-shm"):
                    Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
                os.replace(temporary_db, DB_PATH)
                if not _integrity_ok(DB_PATH):
                    raise ValueError("O banco restaurado não passou na verificação de integridade.")
                if DOCUMENTS_DIR.exists():
                    os.replace(DOCUMENTS_DIR, old_docs)
                os.replace(staged_docs, DOCUMENTS_DIR)
            except BaseException:
                temporary_db.unlink(missing_ok=True)
                if had_db:
                    for suffix in ("-wal", "-shm"):
                        Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
                    shutil.copy2(previous_db, DB_PATH)
                if old_docs.exists() and not DOCUMENTS_DIR.exists():
                    os.replace(old_docs, DOCUMENTS_DIR)
                shutil.rmtree(staged_docs, ignore_errors=True)
                raise
            shutil.rmtree(old_docs, ignore_errors=True)

    return {
        "manifest": manifest,
        "safety_backup": str(safety_backup),
        "restart_required": True,
    }
