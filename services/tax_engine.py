from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# Tabelas vigentes desde 01/01/2018 e usadas por esta versão até 12/2026.
# Valores monetários estão em centavos e alíquotas em formato decimal.
ANNEX_TABLES: dict[str, list[dict[str, Any]]] = {
    "I": [
        {"limit_cents": 18_000_000, "nominal_rate": Decimal("0.0400"), "deduction_cents": 0},
        {"limit_cents": 36_000_000, "nominal_rate": Decimal("0.0730"), "deduction_cents": 594_000},
        {"limit_cents": 72_000_000, "nominal_rate": Decimal("0.0950"), "deduction_cents": 1_386_000},
        {"limit_cents": 180_000_000, "nominal_rate": Decimal("0.1070"), "deduction_cents": 2_250_000},
        {"limit_cents": 360_000_000, "nominal_rate": Decimal("0.1430"), "deduction_cents": 8_730_000},
        {"limit_cents": 480_000_000, "nominal_rate": Decimal("0.1900"), "deduction_cents": 37_800_000},
    ],
    "II": [
        {"limit_cents": 18_000_000, "nominal_rate": Decimal("0.0450"), "deduction_cents": 0},
        {"limit_cents": 36_000_000, "nominal_rate": Decimal("0.0780"), "deduction_cents": 594_000},
        {"limit_cents": 72_000_000, "nominal_rate": Decimal("0.1000"), "deduction_cents": 1_386_000},
        {"limit_cents": 180_000_000, "nominal_rate": Decimal("0.1120"), "deduction_cents": 2_250_000},
        {"limit_cents": 360_000_000, "nominal_rate": Decimal("0.1470"), "deduction_cents": 8_550_000},
        {"limit_cents": 480_000_000, "nominal_rate": Decimal("0.3000"), "deduction_cents": 72_000_000},
    ],
    "III": [
        {"limit_cents": 18_000_000, "nominal_rate": Decimal("0.0600"), "deduction_cents": 0},
        {"limit_cents": 36_000_000, "nominal_rate": Decimal("0.1120"), "deduction_cents": 936_000},
        {"limit_cents": 72_000_000, "nominal_rate": Decimal("0.1350"), "deduction_cents": 1_764_000},
        {"limit_cents": 180_000_000, "nominal_rate": Decimal("0.1600"), "deduction_cents": 3_564_000},
        {"limit_cents": 360_000_000, "nominal_rate": Decimal("0.2100"), "deduction_cents": 12_564_000},
        {"limit_cents": 480_000_000, "nominal_rate": Decimal("0.3300"), "deduction_cents": 64_800_000},
    ],
    "IV": [
        {"limit_cents": 18_000_000, "nominal_rate": Decimal("0.0450"), "deduction_cents": 0},
        {"limit_cents": 36_000_000, "nominal_rate": Decimal("0.0900"), "deduction_cents": 810_000},
        {"limit_cents": 72_000_000, "nominal_rate": Decimal("0.1020"), "deduction_cents": 1_242_000},
        {"limit_cents": 180_000_000, "nominal_rate": Decimal("0.1400"), "deduction_cents": 3_978_000},
        {"limit_cents": 360_000_000, "nominal_rate": Decimal("0.2200"), "deduction_cents": 18_378_000},
        {"limit_cents": 480_000_000, "nominal_rate": Decimal("0.3300"), "deduction_cents": 82_800_000},
    ],
    "V": [
        {"limit_cents": 18_000_000, "nominal_rate": Decimal("0.1550"), "deduction_cents": 0},
        {"limit_cents": 36_000_000, "nominal_rate": Decimal("0.1800"), "deduction_cents": 450_000},
        {"limit_cents": 72_000_000, "nominal_rate": Decimal("0.1950"), "deduction_cents": 990_000},
        {"limit_cents": 180_000_000, "nominal_rate": Decimal("0.2050"), "deduction_cents": 1_710_000},
        {"limit_cents": 360_000_000, "nominal_rate": Decimal("0.2300"), "deduction_cents": 6_210_000},
        {"limit_cents": 480_000_000, "nominal_rate": Decimal("0.3050"), "deduction_cents": 54_000_000},
    ],
}


class TaxEngineError(ValueError):
    pass


def month_index(competence: str) -> int:
    month, year = map(int, competence.split("/"))
    return year * 12 + month - 1


def competence_from_index(value: int) -> str:
    year, month_zero = divmod(value, 12)
    return f"{month_zero + 1:02d}/{year}"


def year_from_competence(competence: str) -> int:
    return int(competence.split("/")[1])


def money_times_rate(cents: int, rate: Decimal) -> int:
    value = Decimal(cents) * rate
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def select_bracket(rbt12_cents: int, annex: str) -> dict[str, Any]:
    if annex not in ANNEX_TABLES:
        raise TaxEngineError("Anexo não suportado.")

    if rbt12_cents < 0:
        raise TaxEngineError("RBT12 não pode ser negativa.")

    for position, bracket in enumerate(ANNEX_TABLES[annex], start=1):
        if rbt12_cents <= bracket["limit_cents"]:
            return {
                **bracket,
                "bracket": position,
            }

    raise TaxEngineError(
        "RBT12 superior ao limite de R$ 4.800.000,00."
    )


def effective_rate(
    rbt12_cents: int,
    annex: str,
) -> dict[str, Any]:
    bracket = select_bracket(rbt12_cents, annex)

    if rbt12_cents == 0:
        rate = bracket["nominal_rate"]
    else:
        numerator = (
            Decimal(rbt12_cents) * bracket["nominal_rate"]
            - Decimal(bracket["deduction_cents"])
        )
        rate = numerator / Decimal(rbt12_cents)

    if rate < 0:
        rate = Decimal("0")

    return {
        "annex": annex,
        "bracket": bracket["bracket"],
        "nominal_rate": str(bracket["nominal_rate"]),
        "deduction_cents": bracket["deduction_cents"],
        "effective_rate": str(
            rate.quantize(
                Decimal("0.0000000001"),
                rounding=ROUND_HALF_UP,
            )
        ),
    }


def build_revenue_timeline(
    pgdas_documents: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """
    Receita do próprio PA prevalece sobre o histórico lido em outro extrato.
    """
    timeline: dict[int, dict[str, Any]] = {}

    for pgdas in pgdas_documents:
        source_file = (
            pgdas.get("source_document", {})
            .get("file_name", "")
        )
        assessment = pgdas.get("assessment", {})

        for row in assessment.get("previous_revenues", []):
            competence = row["competence"]
            index = month_index(competence)

            if index not in timeline:
                timeline[index] = {
                    "competence": competence,
                    "revenue_cents": row["total_cents"],
                    "source": "PREVIOUS_REVENUE_HISTORY",
                    "source_file": source_file,
                }

        period = assessment.get("period", "")
        current_revenue = (
            assessment.get("revenue_summary", {})
            .get("rpa", {})
            .get("total_cents")
        )

        if period and current_revenue is not None:
            timeline[month_index(period)] = {
                "competence": period,
                "revenue_cents": current_revenue,
                "source": "CURRENT_ASSESSMENT",
                "source_file": source_file,
            }

    return timeline


def corrections_from_confirmations(
    confirmations: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    corrections: dict[int, dict[str, Any]] = {}

    for confirmation in confirmations:
        if confirmation.get("decision") not in {
            "CONFIRMED",
            "AUTO_APPROVED",
            "VALIDATED_REGULARIZATION",
        }:
            continue

        analysis = confirmation.get("analysis", {})
        recommendation = analysis.get("recommendation", {})
        increment = (
            recommendation.get(
                "simulation_pgdas_increment_cents"
            )
            if recommendation.get(
                "simulation_pgdas_increment_cents"
            ) is not None
            else recommendation.get(
                "pgdas_increment_cents"
            )
        ) or 0

        if increment <= 0:
            continue

        competence = analysis["competence"]
        corrections[month_index(competence)] = {
            "competence": competence,
            "increment_cents": increment,
            "corrected_revenue_cents": (
                recommendation.get(
                    "simulation_pgdas_revenue_cents"
                )
                if recommendation.get(
                    "simulation_pgdas_revenue_cents"
                ) is not None
                else recommendation.get(
                    "corrected_pgdas_revenue_cents"
                )
            ),
        }

    return corrections


def calculate_hidden_reflections(
    pgdas_documents: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    annex: str,
    standard_profile_confirmed: bool,
    calculation_end_competence: str | None = None,
    full_reflection_end_competence: str | None = None,
    future_pending_competences: list[str] | None = None,
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> dict[str, Any]:
    if not standard_profile_confirmed:
        raise TaxEngineError(
            "Confirme o perfil tributário antes do cálculo."
        )

    if annex not in ANNEX_TABLES:
        raise TaxEngineError("Selecione um anexo entre I e V.")

    timeline = build_revenue_timeline(pgdas_documents)
    corrections = corrections_from_confirmations(confirmations)

    if not corrections:
        return {
            "configuration": {
                "annex": annex,
                "profile": "STANDARD_FULL_REVENUE",
                "scenario": scenario,
                "period_support": "01/2018_TO_12/2026",
            },
            "summary": {
                "corrected_competence_total_cents": 0,
                "reflection_total_cents": 0,
                "estimated_total_cents": 0,
                "impacted_month_count": 0,
                "missing_month_count": 0,
                "unsupported_month_count": 0,
                "calculation_end_competence": None,
                "full_reflection_end_competence": None,
                "future_pending_count": 0,
                "is_partial": False,
            },
            "visible_impacts": [],
            "hidden_timeline": [],
            "missing_months": [],
            "unsupported_months": [],
            "future_pending_competences": [],
            "warnings": [
                "Nenhuma exposição adicional de receita no PGDAS foi identificada."
            ],
        }

    first_index = min(corrections)
    computed_full_last_index = max(corrections) + 12
    full_last_index = (
        month_index(full_reflection_end_competence)
        if full_reflection_end_competence
        else computed_full_last_index
    )
    last_index = (
        min(
            full_last_index,
            month_index(calculation_end_competence),
        )
        if calculation_end_competence
        else full_last_index
    )
    future_pending_competences = (
        future_pending_competences or []
    )

    hidden_timeline: list[dict[str, Any]] = []
    visible_impacts: list[dict[str, Any]] = []
    missing_months: list[dict[str, Any]] = []
    unsupported_months: list[str] = []

    direct_total = 0
    reflection_total = 0

    for target_index in range(first_index, last_index + 1):
        competence = competence_from_index(target_index)

        if year_from_competence(competence) >= 2027:
            unsupported_months.append(competence)
            continue

        required_indexes = list(
            range(target_index - 12, target_index)
        )
        missing = [
            competence_from_index(index)
            for index in required_indexes + [target_index]
            if index not in timeline
        ]

        if missing:
            missing_months.append({
                "competence": competence,
                "missing_competences": sorted(set(missing)),
            })
            continue

        original_revenue = timeline[target_index]["revenue_cents"]
        correction = corrections.get(
            target_index,
            {"increment_cents": 0},
        )["increment_cents"]
        corrected_revenue = original_revenue + correction

        original_rbt12 = sum(
            timeline[index]["revenue_cents"]
            for index in required_indexes
        )
        corrected_rbt12 = sum(
            timeline[index]["revenue_cents"]
            + corrections.get(
                index,
                {"increment_cents": 0},
            )["increment_cents"]
            for index in required_indexes
        )

        original_rate_data = effective_rate(
            original_rbt12,
            annex,
        )
        corrected_rate_data = effective_rate(
            corrected_rbt12,
            annex,
        )

        original_rate = Decimal(
            original_rate_data["effective_rate"]
        )
        corrected_rate = Decimal(
            corrected_rate_data["effective_rate"]
        )

        original_das = money_times_rate(
            original_revenue,
            original_rate,
        )
        corrected_das = money_times_rate(
            corrected_revenue,
            corrected_rate,
        )
        difference = corrected_das - original_das

        is_corrected_competence = correction > 0
        has_rbt12_reflection = corrected_rbt12 != original_rbt12

        if is_corrected_competence and has_rbt12_reflection:
            classification = "CORRECTED_AND_REFLECTION"
        elif is_corrected_competence:
            classification = "CORRECTED_COMPETENCE"
        elif has_rbt12_reflection:
            classification = "RBT12_REFLECTION"
        else:
            classification = "NO_EFFECT"

        row = {
            "competence": competence,
            "classification": classification,
            "original_revenue_cents": original_revenue,
            "revenue_increment_cents": correction,
            "corrected_revenue_cents": corrected_revenue,
            "original_rbt12_cents": original_rbt12,
            "corrected_rbt12_cents": corrected_rbt12,
            "original_bracket": original_rate_data["bracket"],
            "corrected_bracket": corrected_rate_data["bracket"],
            "original_effective_rate": (
                original_rate_data["effective_rate"]
            ),
            "corrected_effective_rate": (
                corrected_rate_data["effective_rate"]
            ),
            "original_das_cents": original_das,
            "corrected_das_cents": corrected_das,
            "difference_cents": difference,
        }
        hidden_timeline.append(row)

        if difference != 0:
            visible_impacts.append(row)

            if is_corrected_competence:
                direct_total += difference
            else:
                reflection_total += difference

    warnings: list[str] = [
        (
            "Cálculo estimativo para receita integralmente tributada "
            "por um único anexo, sem segregações."
        )
    ]

    if missing_months:
        warnings.append(
            "Existem meses sem dados suficientes para concluir todos "
            "os reflexos."
        )

    if future_pending_competences:
        warnings.append(
            "O resultado é parcial até "
            f"{competence_from_index(last_index)}. "
            "Os meses futuros serão recalculados quando os PGDAS "
            "forem transmitidos."
        )

    if unsupported_months:
        warnings.append(
            "Meses de 2027 ou posteriores foram bloqueados porque "
            "exigem as regras da transição tributária."
        )

    return {
        "configuration": {
            "annex": annex,
            "profile": "STANDARD_FULL_REVENUE",
            "scenario": scenario,
            "period_support": "01/2018_TO_12/2026",
        },
        "summary": {
            "corrected_competence_total_cents": direct_total,
            "reflection_total_cents": reflection_total,
            "estimated_total_cents": direct_total + reflection_total,
            "impacted_month_count": len(visible_impacts),
            "missing_month_count": len(missing_months),
            "unsupported_month_count": len(unsupported_months),
            "calculation_end_competence": (
                competence_from_index(last_index)
            ),
            "full_reflection_end_competence": (
                competence_from_index(full_last_index)
            ),
            "future_pending_count": len(
                future_pending_competences
            ),
            "is_partial": bool(future_pending_competences),
        },
        "visible_impacts": visible_impacts,
        "hidden_timeline": hidden_timeline,
        "missing_months": missing_months,
        "unsupported_months": unsupported_months,
        "future_pending_competences": (
            future_pending_competences
        ),
        "warnings": warnings,
    }
