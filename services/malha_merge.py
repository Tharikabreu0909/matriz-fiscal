from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


def _row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("type_code"),
        row.get("reference"),
        int(row.get("informed_cents", 0) or 0),
        int(row.get("considered_cents", 0) or 0),
        int(row.get("divergence_cents", 0) or 0),
    )


def _sort_competence(value: str) -> tuple[int, int]:
    month, year = map(int, value.split("/"))
    return year, month


def _work_months(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["competence"]].append(row)

    result: list[dict[str, Any]] = []
    for competence in sorted(grouped, key=_sort_competence):
        month_rows = grouped[competence]
        types = sorted({row["type_code"] for row in month_rows})
        actions: list[str] = []
        if "01" in types:
            actions.append("REVIEW_AND_RECTIFY_SPED_LFE")
        if "17" in types:
            actions.append("IMPORT_PGDAS_AND_EVALUATE_TAX")

        result.append({
            "competence": competence,
            "types": types,
            "raw_row_count": len(month_rows),
            "unique_notice_count": sum(not row["duplicate"] for row in month_rows),
            "duplicate_count": sum(row["duplicate"] for row in month_rows),
            "raw_row_ids": [row["id"] for row in month_rows],
            "notices": [
                {
                    "type_code": row["type_code"],
                    "informed_field": row.get("informed_field", ""),
                    "informed_cents": row.get("informed_cents", 0),
                    "considered_cents": row.get("considered_cents", 0),
                    "divergence_cents": row.get("divergence_cents", 0),
                    "duplicate": False,
                }
                for row in month_rows
                if not row["duplicate"]
            ],
            "preliminary_actions": actions,
            "status": "AWAITING_CONFIRMATION",
        })
    return result


def source_hashes(malha: dict[str, Any]) -> set[str]:
    sources = malha.get("source_documents") or [
        malha.get("source_document", {})
    ]
    return {
        str(source.get("sha256", "")).strip()
        for source in sources
        if str(source.get("sha256", "")).strip()
    }


def malha_already_imported(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> bool:
    incoming_hash = str(
        incoming.get("source_document", {}).get("sha256", "")
    ).strip()
    return bool(
        incoming_hash
        and incoming_hash in source_hashes(existing)
    )


def merge_malhas(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Preserva todas as linhas e adiciona novas competências ao mesmo processo."""
    if not existing:
        return deepcopy(incoming)

    combined = [deepcopy(row) for row in existing.get("raw_rows", [])]
    combined.extend(deepcopy(row) for row in incoming.get("raw_rows", []))

    first_seen: dict[tuple[Any, ...], int] = {}
    normalized: list[dict[str, Any]] = []
    for source in combined:
        row = deepcopy(source)
        key = _row_key(row)
        row_id = len(normalized) + 1
        duplicate_of = first_seen.get(key)
        if duplicate_of is None:
            first_seen[key] = row_id
        row["id"] = row_id
        row["duplicate"] = duplicate_of is not None
        row["duplicate_of"] = duplicate_of
        normalized.append(row)

    sources: list[dict[str, Any]] = []
    known_hashes: set[str] = set()
    for malha in (existing, incoming):
        candidates = malha.get("source_documents") or [malha.get("source_document", {})]
        for source in candidates:
            if not source:
                continue
            key = source.get("sha256") or source.get("file_name", "")
            if key in known_hashes:
                continue
            known_hashes.add(key)
            sources.append(deepcopy(source))

    notes = []
    for text in (existing.get("explanatory_notes", ""), incoming.get("explanatory_notes", "")):
        text = str(text or "").strip()
        if text and text not in notes:
            notes.append(text)

    work_months = _work_months(normalized)
    contributor = deepcopy(existing.get("contributor", {}))
    contributor.update({
        key: value
        for key, value in incoming.get("contributor", {}).items()
        if value
    })

    return {
        "reader": deepcopy(incoming.get("reader") or existing.get("reader", {})),
        "source_document": deepcopy(incoming.get("source_document", {})),
        "source_documents": sources,
        "contributor": contributor,
        "summary": {
            "raw_row_count": len(normalized),
            "unique_raw_notice_count": sum(not row["duplicate"] for row in normalized),
            "duplicate_row_count": sum(row["duplicate"] for row in normalized),
            "work_month_count": len(work_months),
            "types_found": sorted({row["type_code"] for row in normalized}),
        },
        "raw_rows": normalized,
        "work_months": work_months,
        "explanatory_notes": "\n\n".join(notes),
    }
