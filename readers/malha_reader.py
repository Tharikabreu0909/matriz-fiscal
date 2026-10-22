from __future__ import annotations

from pathlib import Path
from collections import defaultdict
from typing import Any
import hashlib
import json
import re

import pdfplumber


MONEY_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}")
DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
TYPE_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(.+)", re.S)


def parse_money_to_cents(value: str | None) -> int:
    if not value:
        return 0
    match = MONEY_RE.search(value.replace("\n", " "))
    if not match:
        raise ValueError(f"Valor monetário não reconhecido: {value!r}")
    normalized = match.group(0).replace(".", "").replace(",", ".")
    return round(float(normalized) * 100)


def format_cents(cents: int) -> str:
    return f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_reference(value: str) -> tuple[str, str]:
    match = DATE_RE.search(value or "")
    if not match:
        raise ValueError(f"Referência inválida: {value!r}")
    day, month, year = match.groups()
    return f"{day}/{month}/{year}", f"{month}/{year}"


def extract_contributor(page: pdfplumber.page.Page) -> dict[str, str]:
    text = page.extract_text() or ""
    cfdf = re.search(r"CFDF:\s*\n?([0-9./-]+)", text)
    legal_name = re.search(r"Razão Social:\s*\n?(.+)", text)

    return {
        "cfdf": cfdf.group(1).strip() if cfdf else "",
        "legal_name": legal_name.group(1).strip() if legal_name else "",
    }


def find_notice_table(page: pdfplumber.page.Page) -> list[list[str | None]]:
    for table in page.extract_tables():
        if not table:
            continue
        header = " ".join(str(cell or "") for cell in table[0])
        required = ("Tipo de Divergência", "Referência", "Informado", "Divergência")
        if all(item in header for item in required):
            return table
    raise RuntimeError("Tabela de Avisos não encontrada.")


def extract_notes(pages: list[pdfplumber.page.Page]) -> str:
    texts = [page.extract_text() or "" for page in pages]
    first = texts[0]
    marker = "Notas Explicativas"
    start = first.find(marker)
    if start < 0:
        return ""

    note_parts = [first[start + len(marker):]]
    if len(texts) > 1:
        note_parts.extend(texts[1:])

    notes = "\n".join(note_parts)
    notes = re.sub(r"^\d{2}/\d{2}/\d{4},\s*\d{2}:\d{2}.*?$", "", notes, flags=re.M)
    notes = re.sub(r"https?://\S+", "", notes)
    notes = re.sub(r"\s+\d+/\d+\s*$", "", notes)
    notes = re.sub(r"\n{3,}", "\n\n", notes)
    return notes.strip()


def read_malha_pdf(pdf_path: str | Path) -> dict[str, Any]:
    path = Path(pdf_path)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with pdfplumber.open(path) as pdf:
        pages = list(pdf.pages)
        contributor = extract_contributor(pages[0])
        notice_table = find_notice_table(pages[0])
        full_text = "\n".join(page.extract_text() or "" for page in pages)

        queried_at = ""
        queried_match = re.search(
            r"(\d{2}/\d{2}/\d{4}),\s*(\d{2}:\d{2})",
            full_text,
        )
        if queried_match:
            queried_at = f"{queried_match.group(1)} {queried_match.group(2)}"

        source_match = re.search(
            r"(Agenci@Net\s*-\s*Secretaria de Estado de Economia\s*-\s*SEEC DF)",
            full_text,
        )

        raw_rows: list[dict[str, Any]] = []
        current_type_code = ""
        current_type_description = ""
        first_seen: dict[tuple[Any, ...], int] = {}

        for table_row_index, row in enumerate(notice_table[1:], start=1):
            type_cell, reference_cell, informed_cell, considered_cell, divergence_cell = [
                (cell or "").strip() for cell in row
            ]

            if type_cell:
                type_match = TYPE_RE.match(type_cell)
                if not type_match:
                    raise ValueError(f"Tipo de divergência não reconhecido: {type_cell}")
                current_type_code = type_match.group(1).zfill(2)
                current_type_description = " ".join(type_match.group(2).split())

            if not current_type_code:
                raise ValueError("Linha encontrada sem tipo de divergência anterior.")

            reference, competence = normalize_reference(reference_cell)
            informed_cents = parse_money_to_cents(informed_cell)
            considered_cents = parse_money_to_cents(considered_cell)
            divergence_cents = parse_money_to_cents(divergence_cell)

            semantic_field = {
                "01": "SPED_LFE_INFORMED",
                "17": "PGDAS_INFORMED",
            }.get(current_type_code, "GENERIC_INFORMED")

            duplicate_key = (
                current_type_code,
                reference,
                informed_cents,
                considered_cents,
                divergence_cents,
            )
            duplicate_of = first_seen.get(duplicate_key)

            row_id = len(raw_rows) + 1
            if duplicate_of is None:
                first_seen[duplicate_key] = row_id

            raw_rows.append({
                "id": row_id,
                "page": 1,
                "table_row": table_row_index,
                "type_code": current_type_code,
                "type_description": current_type_description,
                "reference": reference,
                "competence": competence,
                "informed_field": semantic_field,
                "informed_cents": informed_cents,
                "considered_cents": considered_cents,
                "divergence_cents": divergence_cents,
                "duplicate": duplicate_of is not None,
                "duplicate_of": duplicate_of,
                "confidence": 1.0,
                "source_cells": {
                    "type": type_cell,
                    "reference": reference_cell,
                    "informed": informed_cell,
                    "considered": considered_cell,
                    "divergence": divergence_cell,
                },
            })

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw_rows:
            grouped[row["competence"]].append(row)

        work_months = []
        for competence in sorted(
            grouped,
            key=lambda value: (int(value.split("/")[1]), int(value.split("/")[0])),
        ):
            rows = grouped[competence]
            types = sorted({row["type_code"] for row in rows})
            unique_rows = [row for row in rows if not row["duplicate"]]
            duplicates = [row for row in rows if row["duplicate"]]

            preliminary_actions = []
            if "01" in types:
                preliminary_actions.append("REVIEW_AND_RECTIFY_SPED_LFE")
            if "17" in types:
                preliminary_actions.append("IMPORT_PGDAS_AND_EVALUATE_TAX")

            work_months.append({
                "competence": competence,
                "types": types,
                "raw_row_count": len(rows),
                "unique_notice_count": len(unique_rows),
                "duplicate_count": len(duplicates),
                "raw_row_ids": [row["id"] for row in rows],
                "notices": [
                    {
                        "type_code": row["type_code"],
                        "informed_field": row["informed_field"],
                        "informed_cents": row["informed_cents"],
                        "considered_cents": row["considered_cents"],
                        "divergence_cents": row["divergence_cents"],
                        "duplicate": row["duplicate"],
                    }
                    for row in unique_rows
                ],
                "preliminary_actions": preliminary_actions,
                "status": "AWAITING_CONFIRMATION",
            })

        return {
            "reader": {
                "name": "checkfiscal-malha-gdf-reader",
                "version": "1.0.0",
            },
            "source_document": {
                "file_name": path.name,
                "sha256": file_hash,
                "page_count": len(pages),
                "queried_at": queried_at,
                "source_system": source_match.group(1) if source_match else "",
            },
            "contributor": contributor,
            "summary": {
                "raw_row_count": len(raw_rows),
                "unique_raw_notice_count": sum(not row["duplicate"] for row in raw_rows),
                "duplicate_row_count": sum(row["duplicate"] for row in raw_rows),
                "work_month_count": len(work_months),
                "types_found": sorted({row["type_code"] for row in raw_rows}),
            },
            "raw_rows": raw_rows,
            "work_months": work_months,
            "explanatory_notes": extract_notes(pages),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default="malha-extraida.json")
    args = parser.parse_args()

    result = read_malha_pdf(args.pdf)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(args.output)
