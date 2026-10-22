from __future__ import annotations

from collections import defaultdict
from typing import Any
import re


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def company_root_from_registered_cnpj(
    registered_cnpj: str,
) -> str:
    identifier = digits(registered_cnpj)
    return identifier[:8] if len(identifier) >= 8 else identifier


def company_root_from_pgdas(pgdas: dict[str, Any]) -> str:
    basic = digits(
        pgdas.get("taxpayer", {}).get("basic_cnpj", "")
    )
    if len(basic) >= 8:
        return basic[:8]

    full = digits(
        (
            pgdas.get("taxpayer", {})
            .get("full_cnpjs_found", [""])[0]
            if pgdas.get("taxpayer", {})
            .get("full_cnpjs_found")
            else ""
        )
    )
    return full[:8] if len(full) >= 8 else full


def validate_pgdas_identity(
    registered_cnpj: str,
    pgdas: dict[str, Any],
) -> dict[str, Any]:
    registered_root = company_root_from_registered_cnpj(
        registered_cnpj
    )
    pgdas_root = company_root_from_pgdas(pgdas)

    if not registered_root or not pgdas_root:
        return {
            "status": "UNCONFIRMED",
            "match": False,
            "registered_root": registered_root,
            "pgdas_root": pgdas_root,
            "message": (
                "Não foi possível confirmar automaticamente "
                "a identidade da empresa."
            ),
        }

    match = registered_root == pgdas_root

    return {
        "status": "MATCH" if match else "MISMATCH",
        "match": match,
        "registered_root": registered_root,
        "pgdas_root": pgdas_root,
        "message": (
            "Empresa confirmada pelo CNPJ cadastrado."
            if match
            else "O PGDAS pertence a outra raiz de CNPJ."
        ),
    }


def build_revenue_index(
    pgdas_documents: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Constrói uma linha declarada única.

    A receita do PA do próprio documento tem prioridade sobre o valor
    histórico de outro extrato.
    """
    index: dict[str, dict[str, Any]] = {}

    for pgdas in pgdas_documents:
        source_file = (
            pgdas.get("source_document", {})
            .get("file_name", "")
        )
        assessment = pgdas.get("assessment", {})

        for item in assessment.get("previous_revenues", []):
            competence = item["competence"]

            if competence not in index:
                index[competence] = {
                    "competence": competence,
                    "declared_revenue_cents": item["total_cents"],
                    "source": "PREVIOUS_REVENUE_HISTORY",
                    "source_file": source_file,
                }

        pa = assessment.get("period", "")
        rpa = (
            assessment.get("revenue_summary", {})
            .get("rpa", {})
            .get("total_cents")
        )

        if pa and rpa is not None:
            index[pa] = {
                "competence": pa,
                "declared_revenue_cents": rpa,
                "source": "CURRENT_ASSESSMENT",
                "source_file": source_file,
            }

    return index


def unique_notices_by_type(
    month: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, ...]] = set()

    for notice in month.get("notices", []):
        key = (
            notice.get("type_code"),
            notice.get("informed_cents"),
            notice.get("considered_cents"),
            notice.get("divergence_cents"),
        )

        if key in seen:
            continue

        seen.add(key)
        grouped[notice["type_code"]].append(notice)

    return dict(grouped)


def cross_malha_with_pgdas(
    malha: dict[str, Any],
    pgdas_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    revenue_index = build_revenue_index(pgdas_documents)
    diagnostics: list[dict[str, Any]] = []

    for month in malha.get("work_months", []):
        competence = month["competence"]
        grouped = unique_notices_by_type(month)
        actions: list[dict[str, Any]] = []
        warnings: list[str] = []
        type_results: dict[str, Any] = {}

        type_01_notices = grouped.get("01", [])

        if len(type_01_notices) > 1:
            warnings.append(
                "A competência possui mais de um aviso tipo 01 "
                "com valores diferentes."
            )

        if type_01_notices:
            notice = type_01_notices[0]
            informed = notice["informed_cents"]
            considered = notice["considered_cents"]
            correction = max(0, considered - informed)

            type_results["01"] = {
                "sped_lfe_informed_cents": informed,
                "considered_cents": considered,
                "correction_cents": correction,
                "status": (
                    "RECTIFICATION_REQUIRED"
                    if correction > 0
                    else "NO_RECTIFICATION_REQUIRED"
                ),
            }

            if correction > 0:
                actions.append({
                    "action": "RECTIFY_SPED_LFE",
                    "amount_cents": correction,
                })

        type_17_notices = grouped.get("17", [])

        if len(type_17_notices) > 1:
            warnings.append(
                "A competência possui mais de um aviso tipo 17 "
                "com valores diferentes."
            )

        if type_17_notices:
            notice = type_17_notices[0]
            malha_informed = notice["informed_cents"]
            considered = notice["considered_cents"]
            declared = revenue_index.get(competence)

            if declared is None:
                type_results["17"] = {
                    "malha_pgdas_informed_cents": malha_informed,
                    "considered_cents": considered,
                    "pgdas_declared_cents": None,
                    "status": "AWAITING_PGDAS_DATA",
                }
            else:
                pgdas_declared = declared["declared_revenue_cents"]
                correction = max(
                    0,
                    considered - pgdas_declared,
                )

                if pgdas_declared != malha_informed:
                    warnings.append(
                        "O valor declarado no PGDAS importado é "
                        "diferente do valor informado na malha. "
                        "O arquivo pode ser uma apuração retificada."
                    )

                type_results["17"] = {
                    "malha_pgdas_informed_cents": malha_informed,
                    "pgdas_declared_cents": pgdas_declared,
                    "considered_cents": considered,
                    "correction_cents": correction,
                    "source": declared,
                    "status": (
                        "RECTIFICATION_REQUIRED"
                        if correction > 0
                        else "NO_RECTIFICATION_REQUIRED"
                    ),
                }

                if correction > 0:
                    actions.extend([
                        {
                            "action": "RECTIFY_PGDAS",
                            "amount_cents": correction,
                        },
                        {
                            "action": "CALCULATE_DIRECT_TAX",
                            "status": "PENDING_TAX_ENGINE",
                        },
                        {
                            "action": "CALCULATE_RBT12_REFLECTIONS",
                            "status": "PENDING_TAX_ENGINE",
                        },
                    ])

        requires_pgdas = bool(type_17_notices)
        has_pgdas_data = (
            not requires_pgdas
            or competence in revenue_index
        )

        if warnings:
            status = "REVIEW_REQUIRED"
        elif requires_pgdas and not has_pgdas_data:
            status = "AWAITING_PGDAS"
        elif actions:
            status = "ACTION_REQUIRED"
        else:
            status = "NO_ACTION_REQUIRED"

        diagnostics.append({
            "competence": competence,
            "types": month.get("types", []),
            "status": status,
            "type_results": type_results,
            "actions": actions,
            "warnings": warnings,
            "raw_row_count": month.get("raw_row_count", 0),
            "duplicate_count": month.get("duplicate_count", 0),
        })

    return {
        "summary": {
            "competence_count": len(diagnostics),
            "action_required_count": sum(
                item["status"] in {
                    "ACTION_REQUIRED",
                    "REVIEW_REQUIRED",
                }
                for item in diagnostics
            ),
            "awaiting_pgdas_count": sum(
                item["status"] == "AWAITING_PGDAS"
                for item in diagnostics
            ),
        },
        "diagnostics": diagnostics,
    }
