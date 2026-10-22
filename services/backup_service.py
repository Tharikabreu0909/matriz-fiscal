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


def restore_backup(content: bytes, app_version: str) -> dict[str, Any]:
    manifest = validate_backup_bytes(content)
    safety_backup = create_backup(app_version)

    with TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        archive_path = temp / "backup.zip"
        archive_path.write_bytes(content)

        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, temp / "extracted")

        extracted = temp / "extracted"
        restored_db = extracted / "database" / "checkfiscal.db"
        check = sqlite3.connect(restored_db)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("O banco do backup não passou na verificação de integridade.")
        finally:
            check.close()

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
        temporary_db = DB_PATH.with_suffix(".restore.tmp")
        shutil.copy2(restored_db, temporary_db)
        os.replace(temporary_db, DB_PATH)

        restored_documents = extracted / "documents"
        if DOCUMENTS_DIR.exists():
            shutil.rmtree(DOCUMENTS_DIR)
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        if restored_documents.exists():
            shutil.copytree(
                restored_documents,
                DOCUMENTS_DIR,
                dirs_exist_ok=True,
            )

    return {
        "manifest": manifest,
        "safety_backup": str(safety_backup),
        "restart_required": True,
    }
