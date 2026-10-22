from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import re
import shutil

from services.runtime_paths import DOCUMENTS_DIR


def _safe_name(value: str) -> str:
    name = Path(str(value or "arquivo.pdf")).name.strip()
    return (name or "arquivo.pdf")[:255]


def store_document(
    *,
    content: bytes,
    company_id: int,
    process_id: int,
    kind: str,
    original_name: str,
    competence: str = "",
) -> dict[str, Any]:
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(original_name).suffix.lower() or ".pdf"
    folder = DOCUMENTS_DIR / f"company-{company_id}" / f"process-{process_id}"
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{kind.lower()}-{digest[:16]}{suffix}"
    target = folder / stored_name

    if not target.exists():
        target.write_bytes(content)

    return {
        "original_name": _safe_name(original_name),
        "stored_path": str(target.relative_to(DOCUMENTS_DIR)),
        "sha256": digest,
        "size_bytes": len(content),
        "kind": kind,
        "competence": competence,
    }


def resolve_document_path(stored_path: str) -> Path:
    candidate = (DOCUMENTS_DIR / stored_path).resolve()
    root = DOCUMENTS_DIR.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Caminho de documento inválido.")
    return candidate


def delete_company_documents(company_id: int) -> None:
    folder = DOCUMENTS_DIR / f"company-{company_id}"
    if folder.exists():
        shutil.rmtree(folder)
