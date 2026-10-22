from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.tax_engine import (
    ANNEX_TABLES,
    TaxEngineError,
    build_revenue_timeline,
    competence_from_index,
    corrections_from_confirmations,
    effective_rate,
    month_index,
    money_times_rate,
    year_from_competence,
)


PROFILE_CODE = "SEGREGATED_REVENUE_V1"
FACTOR_R_THRESHOLD = Decimal("0.28")
SEGREGATION_RBT12_LIMIT_CENTS = 360_000_000


CATEGORY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "COMMERCE_NORMAL": {
        "label": "Comércio normal",
        "annex": "I",
        "excluded_components": [],
    },
    "COMMERCE_MONOPHASIC": {
        "label": "Comércio com PIS/Cofins monofásico",
        "annex": "I",
        "excluded_components": ["COFINS", "PIS"],
    },
    "COMMERCE_ICMS_ST": {
        "label": (
            "Comércio com ICMS-ST ou antecipação "
            "com encerramento"
        ),
        "annex": "I",
        "excluded_components": ["ICMS"],
    },
    "COMMERCE_MONOPHASIC_ICMS_ST": {
        "label": "Comércio monofásico e com ICMS-ST",
        "annex": "I",
        "excluded_components": ["COFINS", "PIS", "ICMS"],
    },
    "INDUSTRY_NORMAL": {
        "label": "Indústria normal",
        "annex": "II",
        "excluded_components": [],
    },
    "SERVICE_III": {
        "label": "Serviço — Anexo III",
        "annex": "III",
        "excluded_components": [],
    },
    "SERVICE_IV": {
        "label": "Serviço — Anexo IV",
        "annex": "IV",
        "excluded_components": [],
    },
    "SERVICE_FACTOR_R": {
        "label": "Serviço sujeito ao Fator R",
        "annex": "FACTOR_R",
        "excluded_components": [],
    },
}


# Percentual de repartição da alíquota efetiva.
# Nesta versão, os percentuais são necessários para retirar PIS/Cofins
# monofásicos e ICMS-ST das receitas do Anexo I.
ANNEX_I_PARTITIONS: dict[int, dict[str, Decimal]] = {
    1: {
        "COFINS": Decimal("0.1274"),
        "PIS": Decimal("0.0276"),
        "ICMS": Decimal("0.3400"),
    },
    2: {
        "COFINS": Decimal("0.1274"),
        "PIS": Decimal("0.0276"),
        "ICMS": Decimal("0.3400"),
    },
    3: {
        "COFINS": Decimal("0.1274"),
        "PIS": Decimal("0.0276"),
        "ICMS": Decimal("0.3350"),
    },
    4: {
        "COFINS": Decimal("0.1274"),
        "PIS": Decimal("0.0276"),
        "ICMS": Decimal("0.3350"),
    },
    5: {
        "COFINS": Decimal("0.1274"),
        "PIS": Decimal("0.0276"),
        "ICMS": Decimal("0.3350"),
    },
}


class TaxSegregationError(TaxEngineError):
    pass


def decimal_text(value: Decimal) -> str:
    return str(
        value.quantize(
            Decimal("0.0000000001"),
            rounding=ROUND_HALF_UP,
        )
    )


def normalize_base_distribution(
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = profile.get("base_distribution", [])

    if not rows:
        raise TaxSegregationError(
            "Informe o perfil das receitas originais."
        )

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_basis_points = 0

    for row in rows:
        category = str(row.get("category", "")).strip()
        basis_points = int(row.get("basis_points", 0) or 0)

        if category not in CATEGORY_DEFINITIONS:
            raise TaxSegregationError(
                f"Categoria tributária inválida: {category}."
            )

        if category in seen:
            raise TaxSegregationError(
                "Não repita uma categoria no perfil original."
            )

        if basis_points < 0:
            raise TaxSegregationError(
                "Os percentuais não podem ser negativos."
            )

        seen.add(category)
        total_basis_points += basis_points

        if basis_points > 0:
            normalized.append({
                "category": category,
                "basis_points": basis_points,
            })

    if total_basis_points != 10_000:
        raise TaxSegregationError(
            "O perfil das receitas originais deve totalizar 100%."
        )

    return normalized


def normalize_correction_allocations(
    profile: dict[str, Any],
    corrections: dict[int, dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    submitted = {
        month_index(row["competence"]): row
        for row in profile.get("correction_allocations", [])
    }
    normalized: dict[int, list[dict[str, Any]]] = {}

    for correction_index, correction in corrections.items():
        competence = correction["competence"]
        expected_total = int(correction["increment_cents"])
        allocation = submitted.get(correction_index)

        if allocation is None:
            raise TaxSegregationError(
                "Distribua a receita adicional da competência "
                f"{competence}."
            )

        category_rows = allocation.get("allocations", [])
        total = 0
        seen: set[str] = set()
        normalized_rows: list[dict[str, Any]] = []

        for row in category_rows:
            category = str(row.get("category", "")).strip()
            amount_cents = int(row.get("amount_cents", 0) or 0)

            if category not in CATEGORY_DEFINITIONS:
                raise TaxSegregationError(
                    f"Categoria tributária inválida em {competence}."
                )

            if category in seen:
                raise TaxSegregationError(
                    f"Categoria repetida em {competence}."
                )

            if amount_cents < 0:
                raise TaxSegregationError(
                    "Os valores distribuídos não podem ser negativos."
                )

            seen.add(category)
            total += amount_cents

            if amount_cents > 0:
                normalized_rows.append({
                    "category": category,
                    "amount_cents": amount_cents,
                })

        if total != expected_total:
            raise TaxSegregationError(
                "A distribuição da competência "
                f"{competence} deve totalizar exatamente "
                f"{expected_total} centavos."
            )

        normalized[correction_index] = normalized_rows

    extra = set(submitted) - set(corrections)

    if extra:
        extra_text = ", ".join(
            competence_from_index(index)
            for index in sorted(extra)
        )
        raise TaxSegregationError(
            "Foram enviadas distribuições sem divergência no cenário: "
            f"{extra_text}."
        )

    return normalized


def normalize_factor_r_payroll(
    profile: dict[str, Any],
) -> dict[int, int]:
    result: dict[int, int] = {}

    for competence, amount in (
        profile.get("factor_r_payroll", {}) or {}
    ).items():
        amount_cents = int(amount or 0)

        if amount_cents < 0:
            raise TaxSegregationError(
                "A folha de salários não pode ser negativa."
            )

        result[month_index(competence)] = amount_cents

    return result


def allocate_by_basis_points(
    total_cents: int,
    distribution: list[dict[str, Any]],
) -> dict[str, int]:
    result: dict[str, int] = {}
    allocated = 0

    for position, row in enumerate(distribution):
        category = row["category"]

        if position == len(distribution) - 1:
            amount = total_cents - allocated
        else:
            amount = int(
                (
                    Decimal(total_cents)
                    * Decimal(row["basis_points"])
                    / Decimal(10_000)
                ).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )
            allocated += amount

        result[category] = amount

    return result


def factor_r_decision(
    payroll_12m_cents: int | None,
    rbt12_cents: int,
    competence: str,
) -> dict[str, Any]:
    if payroll_12m_cents is None:
        raise TaxSegregationError(
            "Informe a folha de salários dos 12 meses anteriores "
            f"para calcular o Fator R de {competence}."
        )

    if rbt12_cents <= 0:
        raise TaxSegregationError(
            "O Fator R não pode ser calculado com RBT12 zerada "
            f"em {competence} nesta versão."
        )

    ratio = Decimal(payroll_12m_cents) / Decimal(rbt12_cents)
    annex = "III" if ratio >= FACTOR_R_THRESHOLD else "V"

    return {
        "payroll_12m_cents": payroll_12m_cents,
        "rbt12_cents": rbt12_cents,
        "factor_r": decimal_text(ratio),
        "threshold": "0.28",
        "annex": annex,
    }


def category_rate(
    category: str,
    rbt12_cents: int,
    competence: str,
    payroll_12m_cents: int | None,
) -> dict[str, Any]:
    definition = CATEGORY_DEFINITIONS[category]
    annex = definition["annex"]
    factor_r = None

    if annex == "FACTOR_R":
        factor_r = factor_r_decision(
            payroll_12m_cents,
            rbt12_cents,
            competence,
        )
        annex = factor_r["annex"]

    rate_data = effective_rate(rbt12_cents, annex)
    effective = Decimal(rate_data["effective_rate"])
    excluded = definition["excluded_components"]
    exclusion_rate = Decimal("0")

    if excluded:
        if annex != "I":
            raise TaxSegregationError(
                "A exclusão de tributos desta versão está limitada "
                "às receitas comerciais do Anexo I."
            )

        if rbt12_cents > SEGREGATION_RBT12_LIMIT_CENTS:
            raise TaxSegregationError(
                "Receitas monofásicas ou com ICMS-ST acima de "
                "R$ 3.600.000,00 de RBT12 exigem tratamento de "
                "sublimites ainda não suportado nesta versão."
            )

        partition = ANNEX_I_PARTITIONS[
            rate_data["bracket"]
        ]
        exclusion_rate = sum(
            partition[component]
            for component in excluded
        )

    applicable = effective * (
        Decimal("1") - exclusion_rate
    )

    return {
        "category": category,
        "category_label": definition["label"],
        "annex": annex,
        "bracket": rate_data["bracket"],
        "full_effective_rate": rate_data["effective_rate"],
        "excluded_components": excluded,
        "excluded_share": decimal_text(exclusion_rate),
        "applicable_rate": decimal_text(applicable),
        "factor_r": factor_r,
    }


def segment_tax(
    segments: dict[str, int],
    rbt12_cents: int,
    competence: str,
    payroll_12m_cents: int | None,
) -> dict[str, Any]:
    total_tax = 0
    details: list[dict[str, Any]] = []

    for category, amount_cents in segments.items():
        if amount_cents == 0:
            continue

        rate = category_rate(
            category,
            rbt12_cents,
            competence,
            payroll_12m_cents,
        )
        tax_cents = money_times_rate(
            amount_cents,
            Decimal(rate["applicable_rate"]),
        )
        total_tax += tax_cents
        details.append({
            **rate,
            "revenue_cents": amount_cents,
            "tax_cents": tax_cents,
        })

    return {
        "total_tax_cents": total_tax,
        "details": details,
    }


def weighted_rate(
    tax_cents: int,
    revenue_cents: int,
) -> str:
    if revenue_cents <= 0:
        return "0"

    return decimal_text(
        Decimal(tax_cents) / Decimal(revenue_cents)
    )


def calculate_segmented_reflections(
    pgdas_documents: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    profile: dict[str, Any],
    calculation_end_competence: str | None = None,
    full_reflection_end_competence: str | None = None,
    future_pending_competences: list[str] | None = None,
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> dict[str, Any]:
    base_distribution = normalize_base_distribution(profile)
    timeline = build_revenue_timeline(pgdas_documents)
    corrections = corrections_from_confirmations(confirmations)
    allocations = normalize_correction_allocations(
        profile,
        corrections,
    )
    payroll_by_index = normalize_factor_r_payroll(profile)

    if not corrections:
        return {
            "configuration": {
                "annex": "MIXED",
                "profile": PROFILE_CODE,
                "scenario": scenario,
                "period_support": "01/2018_TO_12/2026",
                "base_distribution": base_distribution,
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
            "factor_r_decisions": [],
            "warnings": [
                "Nenhuma exposição adicional de receita no PGDAS "
                "foi identificada."
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
    factor_r_decisions: list[dict[str, Any]] = []
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

        original_revenue = timeline[target_index][
            "revenue_cents"
        ]
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

        original_segments = allocate_by_basis_points(
            original_revenue,
            base_distribution,
        )
        corrected_segments = dict(original_segments)

        for row in allocations.get(target_index, []):
            category = row["category"]
            corrected_segments[category] = (
                corrected_segments.get(category, 0)
                + row["amount_cents"]
            )

        payroll = payroll_by_index.get(target_index)
        original_tax = segment_tax(
            original_segments,
            original_rbt12,
            competence,
            payroll,
        )
        corrected_tax = segment_tax(
            corrected_segments,
            corrected_rbt12,
            competence,
            payroll,
        )
        difference = (
            corrected_tax["total_tax_cents"]
            - original_tax["total_tax_cents"]
        )

        is_corrected_competence = correction > 0
        has_rbt12_reflection = (
            corrected_rbt12 != original_rbt12
        )

        if is_corrected_competence and has_rbt12_reflection:
            classification = "CORRECTED_AND_REFLECTION"
        elif is_corrected_competence:
            classification = "CORRECTED_COMPETENCE"
        elif has_rbt12_reflection:
            classification = "RBT12_REFLECTION"
        else:
            classification = "NO_EFFECT"

        category_names = sorted(
            set(original_segments) | set(corrected_segments)
        )
        segment_details: list[dict[str, Any]] = []

        for category in category_names:
            original_detail = next(
                (
                    row
                    for row in original_tax["details"]
                    if row["category"] == category
                ),
                None,
            )
            corrected_detail = next(
                (
                    row
                    for row in corrected_tax["details"]
                    if row["category"] == category
                ),
                None,
            )
            reference = corrected_detail or original_detail

            if reference is None:
                continue

            segment_details.append({
                "category": category,
                "category_label": reference[
                    "category_label"
                ],
                "original_revenue_cents": (
                    original_segments.get(category, 0)
                ),
                "corrected_revenue_cents": (
                    corrected_segments.get(category, 0)
                ),
                "original_tax_cents": (
                    original_detail["tax_cents"]
                    if original_detail
                    else 0
                ),
                "corrected_tax_cents": (
                    corrected_detail["tax_cents"]
                    if corrected_detail
                    else 0
                ),
                "difference_cents": (
                    (
                        corrected_detail["tax_cents"]
                        if corrected_detail
                        else 0
                    )
                    - (
                        original_detail["tax_cents"]
                        if original_detail
                        else 0
                    )
                ),
                "original_annex": (
                    original_detail["annex"]
                    if original_detail
                    else None
                ),
                "corrected_annex": (
                    corrected_detail["annex"]
                    if corrected_detail
                    else None
                ),
                "original_rate": (
                    original_detail["applicable_rate"]
                    if original_detail
                    else "0"
                ),
                "corrected_rate": (
                    corrected_detail["applicable_rate"]
                    if corrected_detail
                    else "0"
                ),
                "excluded_components": reference[
                    "excluded_components"
                ],
                "original_factor_r": (
                    original_detail.get("factor_r")
                    if original_detail
                    else None
                ),
                "corrected_factor_r": (
                    corrected_detail.get("factor_r")
                    if corrected_detail
                    else None
                ),
            })

        for detail in (
            original_tax["details"]
            + corrected_tax["details"]
        ):
            factor_r = detail.get("factor_r")

            if factor_r:
                decision = {
                    "competence": competence,
                    "basis": (
                        "CORRECTED"
                        if detail in corrected_tax["details"]
                        else "ORIGINAL"
                    ),
                    **factor_r,
                }

                if decision not in factor_r_decisions:
                    factor_r_decisions.append(decision)

        row = {
            "competence": competence,
            "classification": classification,
            "original_revenue_cents": original_revenue,
            "revenue_increment_cents": correction,
            "corrected_revenue_cents": corrected_revenue,
            "original_rbt12_cents": original_rbt12,
            "corrected_rbt12_cents": corrected_rbt12,
            "original_bracket": "MIXED",
            "corrected_bracket": "MIXED",
            "original_effective_rate": weighted_rate(
                original_tax["total_tax_cents"],
                original_revenue,
            ),
            "corrected_effective_rate": weighted_rate(
                corrected_tax["total_tax_cents"],
                corrected_revenue,
            ),
            "original_das_cents": original_tax[
                "total_tax_cents"
            ],
            "corrected_das_cents": corrected_tax[
                "total_tax_cents"
            ],
            "difference_cents": difference,
            "segments": segment_details,
        }
        hidden_timeline.append(row)

        if difference != 0:
            visible_impacts.append(row)

            if is_corrected_competence:
                direct_total += difference
            else:
                reflection_total += difference

    warnings = [
        (
            "O perfil percentual informado foi aplicado às receitas "
            "originais de todos os meses calculados. Confirme se ele "
            "representa a composição real do período."
        ),
        (
            "Receitas monofásicas dependem da validação dos produtos "
            "e operações. O CheckFiscal não classifica NCM "
            "automaticamente nesta versão."
        ),
        (
            "A opção ICMS-ST é exclusiva do contribuinte substituído "
            "ou da antecipação com encerramento. O substituto "
            "tributário recolhe o ICMS próprio no Simples."
        ),
    ]

    if factor_r_decisions:
        warnings.append(
            "O Fator R foi calculado com a folha de 12 meses "
            "informada pelo contador em cada competência."
        )

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
            "annex": "MIXED",
            "profile": PROFILE_CODE,
            "scenario": scenario,
            "period_support": "01/2018_TO_12/2026",
            "base_distribution": base_distribution,
            "category_definitions": CATEGORY_DEFINITIONS,
        },
        "summary": {
            "corrected_competence_total_cents": direct_total,
            "reflection_total_cents": reflection_total,
            "estimated_total_cents": (
                direct_total + reflection_total
            ),
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
        "factor_r_decisions": factor_r_decisions,
        "warnings": warnings,
    }
