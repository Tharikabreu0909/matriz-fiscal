from __future__ import annotations

from typing import Any

from services.tax_engine import TaxEngineError
from services.tax_revenue_lines import (
    PROFILE_CODE as REVENUE_LINES_PROFILE_CODE,
    calculate_revenue_line_reflections,
)


PROFILE_CODE = "ANNEX_COLUMNS_V4"
ALLOWED_ANNEXES = {"I", "II", "III", "IV", "V"}


class AnnexColumnsError(TaxEngineError):
    pass


def normalize_annexes(
    values: list[str],
    field_label: str,
) -> list[str]:
    annexes = [str(value).strip() for value in values]
    annexes = list(dict.fromkeys(annexes))

    if not annexes:
        raise AnnexColumnsError(
            f"Marque ao menos um anexo para {field_label}."
        )

    if set(annexes) - ALLOWED_ANNEXES:
        raise AnnexColumnsError(
            f"Existe anexo inválido em {field_label}."
        )

    return annexes


def normalize_allocation(
    raw: dict[str, Any],
    annexes: list[str],
    expected_total_cents: int,
    competence: str,
    label: str,
) -> dict[str, int]:
    normalized: dict[str, int] = {}

    for annex in annexes:
        amount = int(raw.get(annex, 0) or 0)

        if amount < 0:
            raise AnnexColumnsError(
                f"Os valores de {label} em {competence} não podem ser negativos."
            )

        normalized[annex] = amount

    unexpected = {
        str(key)
        for key, value in raw.items()
        if str(key) not in annexes and int(value or 0) != 0
    }

    if unexpected:
        raise AnnexColumnsError(
            f"Existe valor informado em anexo não selecionado para {label} de {competence}."
        )

    total = sum(normalized.values())

    if total != expected_total_cents:
        raise AnnexColumnsError(
            f"A distribuição de {label} em {competence} deve fechar exatamente "
            f"em {expected_total_cents} centavos."
        )

    return normalized


def line_for_annex(
    annex: str,
    amount_cents: int,
) -> dict[str, Any]:
    return {
        "amount_cents": amount_cents,
        "activity": annex,
        "pis_monophase": False,
        "cofins_monophase": False,
        "icms_st": False,
    }


def build_revenue_lines_profile(
    profile: dict[str, Any],
    tax_setup: dict[str, Any],
) -> dict[str, Any]:
    declared_annexes = normalize_annexes(
        profile.get("declared_annexes", []),
        "a receita declarada",
    )
    same_annexes = bool(profile.get("same_annexes", True))
    rectified_annexes = (
        declared_annexes
        if same_annexes
        else normalize_annexes(
            profile.get("rectified_annexes", []),
            "a receita acrescentada na retificação",
        )
    )

    submitted = {
        row["competence"]: row
        for row in profile.get("monthly_allocations", [])
    }
    monthly_allocations: list[dict[str, Any]] = []

    for month in tax_setup.get("months", []):
        if not month.get("available"):
            continue

        competence = month["competence"]
        row = submitted.get(competence)

        if row is None:
            raise AnnexColumnsError(
                f"Distribua os valores da competência {competence}."
            )

        declared = normalize_allocation(
            row.get("declared", {}),
            declared_annexes,
            int(month["original_revenue_cents"]),
            competence,
            "receita declarada",
        )
        divergence = normalize_allocation(
            row.get("divergence", {}),
            rectified_annexes,
            int(month["additional_revenue_cents"]),
            competence,
            "divergência",
        )

        monthly_allocations.append({
            "competence": competence,
            "original_lines": [
                line_for_annex(annex, amount)
                for annex, amount in declared.items()
                if amount > 0
            ],
            "additional_lines": [
                line_for_annex(annex, amount)
                for annex, amount in divergence.items()
                if amount > 0
            ],
        })

    setup_competences = {
        month["competence"]
        for month in tax_setup.get("months", [])
        if month.get("available")
    }
    extras = set(submitted) - setup_competences

    if extras:
        raise AnnexColumnsError(
            "Foram enviadas competências fora da janela do cálculo: "
            + ", ".join(sorted(extras))
            + "."
        )

    return {
        "version": REVENUE_LINES_PROFILE_CODE,
        "options": {
            "enabled_activities": list(
                dict.fromkeys(declared_annexes + rectified_annexes)
            ),
            "enabled_treatments": [],
        },
        "monthly_allocations": monthly_allocations,
        "factor_r_payroll": {},
    }


def calculate_annex_columns_reflections(
    pgdas_documents: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    profile: dict[str, Any],
    tax_setup: dict[str, Any],
    calculation_end_competence: str | None = None,
    full_reflection_end_competence: str | None = None,
    future_pending_competences: list[str] | None = None,
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> dict[str, Any]:
    generated_profile = build_revenue_lines_profile(
        profile,
        tax_setup,
    )
    result = calculate_revenue_line_reflections(
        pgdas_documents=pgdas_documents,
        confirmations=confirmations,
        profile=generated_profile,
        calculation_end_competence=calculation_end_competence,
        full_reflection_end_competence=full_reflection_end_competence,
        future_pending_competences=future_pending_competences,
        scenario=scenario,
    )
    result["configuration"]["profile"] = PROFILE_CODE
    result["configuration"]["annex_columns_profile"] = profile
    result["configuration"]["generated_profile"] = generated_profile
    result["warnings"] = [
        "O resultado é uma estimativa fiscal baseada nos anexos e valores distribuídos pelo contador.",
        "A receita acrescentada na retificação foi somada à receita declarada para formar o cenário corrigido.",
        *[
            warning
            for warning in result.get("warnings", [])
            if "monofás" not in warning.lower()
            and "icms-st" not in warning.lower()
            and "fator r" not in warning.lower()
        ],
    ]
    return result
