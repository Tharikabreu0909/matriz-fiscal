from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import platform
import sqlite3
import zipfile

from services.app_logging import LOG_PATH
from services.runtime_paths import DB_PATH, SUPPORT_DIR


def create_support_bundle(app_version: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output = SUPPORT_DIR / f"checkfiscal-diagnostico-{stamp}.zip"

    with TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            tables = [
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                if not row["name"].startswith("sqlite_")
            ]
            counts = {}
            for table in tables:
                counts[table] = int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

        diagnostic = {
            "product": "CheckFiscal",
            "app_version": app_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database_integrity": integrity,
            "database_user_version": user_version,
            "record_counts": counts,
            "note": "Este pacote não inclui PDFs nem valores fiscais extraídos.",
        }
        (temp / "diagnostico.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if LOG_PATH.exists():
            log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            (temp / "checkfiscal.log").write_text(
                log_text[-500_000:],
                encoding="utf-8",
            )

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in temp.iterdir():
                archive.write(file, file.name)

    return output
