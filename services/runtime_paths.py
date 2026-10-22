from __future__ import annotations

from pathlib import Path
import os
import shutil


BASE_DIR = Path(__file__).resolve().parents[1]


def _default_data_dir() -> Path:
    configured = os.environ.get("CHECKFISCAL_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / "CheckFiscal"

    return BASE_DIR / "checkfiscal_data"


DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEGACY_DB_PATH = BASE_DIR / "checkfiscal_local.db"
DB_PATH = Path(
    os.environ.get(
        "CHECKFISCAL_DB_PATH",
        str(DATA_DIR / "checkfiscal.db"),
    )
).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Migração transparente quando o banco antigo foi copiado para a nova pasta.
if (
    "CHECKFISCAL_DB_PATH" not in os.environ
    and not DB_PATH.exists()
    and LEGACY_DB_PATH.exists()
):
    shutil.copy2(LEGACY_DB_PATH, DB_PATH)

DOCUMENTS_DIR = DATA_DIR / "documents"
BACKUPS_DIR = DATA_DIR / "backups"
LOGS_DIR = DATA_DIR / "logs"
SUPPORT_DIR = DATA_DIR / "support"

for directory in (
    DOCUMENTS_DIR,
    BACKUPS_DIR,
    LOGS_DIR,
    SUPPORT_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
