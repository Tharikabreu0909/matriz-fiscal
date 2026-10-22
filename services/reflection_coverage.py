from __future__ import annotations

from datetime import date
from typing import Any

from services.legal_charges import standard_due_date
from services.tax_engine import build_revenue_timeline


HISTORY_MONTHS = 24


def month_index(competence: str) -> int:
    month, year = map(int, competence.split("/"))
    return year * 12 + month - 1


def competence_from_index(value: int) -> str:
    year, zero_based_month = divmod(value, 12)
    return f"{zero_based_month + 1:02d}/{year}"


def previous_month(competence: str) -> str:
    return competence_from_index(month_index(competence) - 1)


def latest_normally_due_competence(
    as_of_date: date | None = None,
) -> str:
    """
    Retorna o PA mais recente cujo vencimento padrão já ocorreu.
    """
    reference = as_of_date or date.today()
    candidate = competence_from_index(
        reference.year * 12 + reference.month - 2
    )

    while standard_due_date(candidate) > reference:
        candidate = previous_month(candidate)

    return candidate


def correction_indexes(
    effective_confirmations: list[dict[str, Any]],
) -> list[int]:
    result: list[int] = []

    for confirmation in effective_confirmations:
        if confirmation.get("decision") not in {
            "CONFIRMED",
            "AUTO_APPROVED",
            "VALIDATED_REGULARIZATION",
        }:
            continue

        analysis = confirmation.get("analysis", {})
        recommendation = analysis.get(
            "recommendation",
            {},
        )
        increment = (
            recommendation.get(
                "simulation_pgdas_increment_cents"
            )
            if recommendation.get(
                "simulation_pgdas_increment_cents"
            ) is not None
            else recommendation.get(
                "pgdas_increment_cents",
                0,
            )
        )

        if increment > 0:
            result.append(month_index(analysis["competence"]))

    return sorted(set(result))


def calculate_reflection_coverage(
    pgdas_documents: list[dict[str, Any]],
    effective_confirmations: list[dict[str, Any]],
    as_of_date: date | None = None,
    history_months: int = HISTORY_MONTHS,
) -> dict[str, Any]:
    corrections = correction_indexes(effective_confirmations)
    latest_due = latest_normally_due_competence(as_of_date)
    latest_due_index = month_index(latest_due)
    timeline = build_revenue_timeline(pgdas_documents)
    accepted_periods = {
        pgdas.get("assessment", {}).get("period", "")
        for pgdas in pgdas_documents
    }

    if not corrections:
        return {
            "status": "NOT_APPLICABLE",
            "closed_months_complete": True,
            "tax_calculation_allowed": True,
            "latest_normally_due_competence": latest_due,
            "full_reflection_end": None,
            "actual_calculation_end": None,
            "supplemental_requests": [],
            "missing_closed_competences": [],
            "future_pending_competences": [],
            "correction_competences": [],
            "description": (
                "Nenhuma correção de receita no PGDAS exige "
                "cobertura posterior."
            ),
        }

    full_end_index = max(index + 12 for index in corrections)
    actual_end_index = min(full_end_index, latest_due_index)

    required_closed_indexes: set[int] = set()

    for correction_index in corrections:
        correction_actual_end = min(
            correction_index + 12,
            latest_due_index,
        )
        required_closed_indexes.update(
            range(correction_index + 1, correction_actual_end + 1)
        )

    missing_closed_indexes = sorted(
        index
        for index in required_closed_indexes
        if index not in timeline
    )
    remaining = set(missing_closed_indexes)
    requests: list[dict[str, Any]] = []

    while remaining:
        requested_index = max(remaining)
        requested_competence = competence_from_index(
            requested_index
        )
        coverage_start_index = requested_index - history_months
        covered = sorted(
            index
            for index in remaining
            if coverage_start_index <= index <= requested_index
        )

        if requested_competence not in accepted_periods:
            requests.append({
                "requested_competence": requested_competence,
                "purpose": "REFLECTION_COVERAGE",
                "covers_reflection_competences": [
                    competence_from_index(index)
                    for index in covered
                ],
                "coverage_start": competence_from_index(
                    coverage_start_index
                ),
                "coverage_end": requested_competence,
                "status": "AWAITING_UPLOAD",
                "selection_rule": (
                    "LATEST_MISSING_CLOSED_REFLECTION_COMPETENCE"
                ),
                "description": (
                    "Necessário para obter as receitas posteriores "
                    "e calcular os reflexos reais da RBT12."
                ),
            })

        for index in covered:
            remaining.discard(index)

    requests.sort(
        key=lambda item: month_index(
            item["requested_competence"]
        )
    )

    future_pending_indexes = (
        list(range(actual_end_index + 1, full_end_index + 1))
        if full_end_index > actual_end_index
        else []
    )

    closed_complete = len(missing_closed_indexes) == 0

    if requests and future_pending_indexes:
        status = "NEEDS_SUPPLEMENTAL_AND_FUTURE_PENDING"
    elif requests:
        status = "NEEDS_SUPPLEMENTAL_PGDAS"
    elif future_pending_indexes:
        status = "ACTUAL_COMPLETE_FUTURE_PENDING"
    else:
        status = "FULLY_COVERED"

    correction_competences = [
        competence_from_index(index)
        for index in corrections
    ]

    if closed_complete and future_pending_indexes:
        description = (
            "Os meses já vencidos estão cobertos. Os meses futuros "
            "serão incorporados quando os respectivos PGDAS forem "
            "transmitidos."
        )
    elif closed_complete:
        description = (
            "A janela completa de reflexos possui receitas reais."
        )
    else:
        description = (
            "Faltam PGDAS posteriores para calcular todos os meses "
            "já vencidos com receitas reais."
        )

    return {
        "status": status,
        "closed_months_complete": closed_complete,
        "tax_calculation_allowed": closed_complete,
        "latest_normally_due_competence": latest_due,
        "full_reflection_end": competence_from_index(
            full_end_index
        ),
        "actual_calculation_end": competence_from_index(
            actual_end_index
        ),
        "supplemental_requests": requests,
        "missing_closed_competences": [
            competence_from_index(index)
            for index in missing_closed_indexes
        ],
        "future_pending_competences": [
            competence_from_index(index)
            for index in future_pending_indexes
        ],
        "correction_competences": correction_competences,
        "description": description,
    }
