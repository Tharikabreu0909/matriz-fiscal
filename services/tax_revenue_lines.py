from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.tax_engine import (
    TaxEngineError,
    build_revenue_timeline,
    competence_from_index,
    corrections_from_confirmations,
    effective_rate,
    month_index,
    money_times_rate,
    year_from_competence,
)
from services.tax_segregation import (
    ANNEX_I_PARTITIONS,
    FACTOR_R_THRESHOLD,
    SEGREGATION_RBT12_LIMIT_CENTS,
    decimal_text,
    factor_r_decision,
)


PROFILE_CODE = "REVENUE_LINES_V2"

ALLOWED_ACTIVITIES = {
    "I",
    "II",
    "III",
    "IV",
    "V",
    "FACTOR_R",
}

ALLOWED_TREATMENTS = {
    "PIS_MONOPHASIC",
    "COFINS_MONOPHASIC",
    "ICMS_ST",
}

ACTIVITY_LABELS = {
    "I": "Anexo I — Comércio",
    "II": "Anexo II — Indústria",
    "III": "Anexo III — Serviços",
    "IV": "Anexo IV — Serviços",
    "V": "Anexo V — Serviços",
    "FACTOR_R": "Serviço sujeito ao Fator R",
}

TREATMENT_LABELS = {
    "PIS_MONOPHASIC": "PIS monofásico",
    "COFINS_MONOPHASIC": "Cofins monofásica",
    "ICMS_ST": "ICMS-ST — contribuinte substituído",
}


class RevenueLinesError(TaxEngineError):
    pass


def normalize_options(
    profile: dict[str, Any],
) -> dict[str, list[str]]:
    options = profile.get("options", {})
    activities = [
        str(value).strip()
        for value in options.get("enabled_activities", [])
    ]
    treatments = [
        str(value).strip()
        for value in options.get("enabled_treatments", [])
    ]

    if not activities:
        raise RevenueLinesError(
            "Marque pelo menos um anexo ou a opção Fator R."
        )

    invalid_activities = set(activities) - ALLOWED_ACTIVITIES
    invalid_treatments = set(treatments) - ALLOWED_TREATMENTS

    if invalid_activities:
        raise RevenueLinesError(
            "Foi selecionada uma atividade tributária inválida."
        )

    if invalid_treatments:
        raise RevenueLinesError(
            "Foi selecionado um tratamento tributário inválido."
        )

    return {
        "enabled_activities": list(dict.fromkeys(activities)),
        "enabled_treatments": list(dict.fromkeys(treatments)),
    }


def line_signature(
    line: dict[str, Any],
) -> tuple[str, bool, bool, bool]:
    return (
        line["activity"],
        bool(line.get("pis_monophase")),
        bool(line.get("cofins_monophase")),
        bool(line.get("icms_st")),
    )


def line_label(
    line: dict[str, Any],
) -> str:
    labels = [ACTIVITY_LABELS[line["activity"]]]

    if line.get("pis_monophase"):
        labels.append("PIS monofásico")

    if line.get("cofins_monophase"):
        labels.append("Cofins monofásica")

    if line.get("icms_st"):
        labels.append("ICMS-ST")

    return " · ".join(labels)


def normalize_line(
    line: dict[str, Any],
    options: dict[str, list[str]],
    competence: str,
) -> dict[str, Any] | None:
    amount_cents = int(line.get("amount_cents", 0) or 0)

    if amount_cents < 0:
        raise RevenueLinesError(
            f"Os valores de {competence} não podem ser negativos."
        )

    if amount_cents == 0:
        return None

    activity = str(line.get("activity", "")).strip()

    if activity not in ALLOWED_ACTIVITIES:
        raise RevenueLinesError(
            f"Selecione uma atividade válida em {competence}."
        )

    if activity not in options["enabled_activities"]:
        raise RevenueLinesError(
            f"A atividade {ACTIVITY_LABELS[activity]} não está "
            f"habilitada nas chaves de {competence}."
        )

    normalized = {
        "amount_cents": amount_cents,
        "activity": activity,
        "pis_monophase": bool(
            line.get("pis_monophase", False)
        ),
        "cofins_monophase": bool(
            line.get("cofins_monophase", False)
        ),
        "icms_st": bool(line.get("icms_st", False)),
    }

    selected_treatments = {
        treatment
        for treatment, enabled in (
            (
                "PIS_MONOPHASIC",
                normalized["pis_monophase"],
            ),
            (
                "COFINS_MONOPHASIC",
                normalized["cofins_monophase"],
            ),
            ("ICMS_ST", normalized["icms_st"]),
        )
        if enabled
    }

    unavailable = selected_treatments - set(
        options["enabled_treatments"]
    )

    if unavailable:
        raise RevenueLinesError(
            f"Existe tratamento não habilitado em {competence}."
        )

    if selected_treatments and activity != "I":
        raise RevenueLinesError(
            "PIS/Cofins monofásicos e ICMS-ST estão limitados "
            f"às linhas do Anexo I em {competence} nesta versão."
        )

    return normalized


def normalize_line_group(
    lines: list[dict[str, Any]],
    expected_total_cents: int,
    options: dict[str, list[str]],
    competence: str,
    group_label: str,
) -> list[dict[str, Any]]:
    normalized = [
        value
        for line in lines
        if (
            value := normalize_line(
                line,
                options,
                competence,
            )
        )
        is not None
    ]
    total = sum(
        line["amount_cents"]
        for line in normalized
    )

    if total != expected_total_cents:
        raise RevenueLinesError(
            f"A {group_label} de {competence} deve fechar "
            f"exatamente em {expected_total_cents} centavos."
        )

    return normalized


def normalize_monthly_allocations(
    profile: dict[str, Any],
    timeline: dict[int, dict[str, Any]],
    corrections: dict[int, dict[str, Any]],
    first_index: int,
    last_index: int,
    options: dict[str, list[str]],
) -> dict[int, dict[str, Any]]:
    submitted = {
        month_index(row["competence"]): row
        for row in profile.get("monthly_allocations", [])
    }
    normalized: dict[int, dict[str, Any]] = {}

    for target_index in range(first_index, last_index + 1):
        if target_index not in timeline:
            continue

        competence = competence_from_index(target_index)
        row = submitted.get(target_index)

        if row is None:
            raise RevenueLinesError(
                "Classifique as receitas da competência "
                f"{competence}."
            )

        original_total = timeline[target_index][
            "revenue_cents"
        ]
        additional_total = int(
            corrections.get(
                target_index,
                {"increment_cents": 0},
            )["increment_cents"]
        )

        normalized[target_index] = {
            "competence": competence,
            "original_lines": normalize_line_group(
                row.get("original_lines", []),
                original_total,
                options,
                competence,
                "receita original",
            ),
            "additional_lines": normalize_line_group(
                row.get("additional_lines", []),
                additional_total,
                options,
                competence,
                "receita adicional",
            ),
        }

    allowed_indexes = {
        index
        for index in range(first_index, last_index + 1)
        if index in timeline
    }
    extras = set(submitted) - allowed_indexes

    if extras:
        extra_text = ", ".join(
            competence_from_index(index)
            for index in sorted(extras)
        )
        raise RevenueLinesError(
            "Foram enviadas classificações fora da janela "
            f"do cálculo: {extra_text}."
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
            raise RevenueLinesError(
                "A folha de salários não pode ser negativa."
            )

        result[month_index(competence)] = amount_cents

    return result


def line_rate(
    line: dict[str, Any],
    rbt12_cents: int,
    competence: str,
    payroll_12m_cents: int | None,
) -> dict[str, Any]:
    activity = line["activity"]
    annex = activity
    factor_r = None

    if activity == "FACTOR_R":
        factor_r = factor_r_decision(
            payroll_12m_cents,
            rbt12_cents,
            competence,
        )
        annex = factor_r["annex"]

    rate_data = effective_rate(
        rbt12_cents,
        annex,
    )
    effective = Decimal(
        rate_data["effective_rate"]
    )
    selected_components: list[str] = []

    if line.get("pis_monophase"):
        selected_components.append("PIS")

    if line.get("cofins_monophase"):
        selected_components.append("COFINS")

    if line.get("icms_st"):
        selected_components.append("ICMS")

    excluded_share = Decimal("0")

    if selected_components:
        if annex != "I":
            raise RevenueLinesError(
                "Os tratamentos especiais desta versão são "
                "aplicáveis somente ao Anexo I."
            )

        if rbt12_cents > SEGREGATION_RBT12_LIMIT_CENTS:
            raise RevenueLinesError(
                "Tratamentos especiais acima de "
                "R$ 3.600.000,00 de RBT12 exigem regras de "
                "sublimite ainda não suportadas."
            )

        partition = ANNEX_I_PARTITIONS[
            rate_data["bracket"]
        ]
        excluded_share = sum(
            partition[component]
            for component in selected_components
        )

    applicable = effective * (
        Decimal("1") - excluded_share
    )

    return {
        "activity": activity,
        "activity_label": ACTIVITY_LABELS[activity],
        "annex": annex,
        "bracket": rate_data["bracket"],
        "full_effective_rate": rate_data[
            "effective_rate"
        ],
        "applicable_rate": decimal_text(applicable),
        "excluded_components": selected_components,
        "excluded_share": decimal_text(excluded_share),
        "factor_r": factor_r,
        "line_label": line_label(line),
    }


def calculate_line_group_tax(
    lines: list[dict[str, Any]],
    rbt12_cents: int,
    competence: str,
    payroll_12m_cents: int | None,
) -> dict[str, Any]:
    total_tax = 0
    details: list[dict[str, Any]] = []

    for line in lines:
        rate = line_rate(
            line,
            rbt12_cents,
            competence,
            payroll_12m_cents,
        )
        tax_cents = money_times_rate(
            line["amount_cents"],
            Decimal(rate["applicable_rate"]),
        )
        total_tax += tax_cents
        details.append({
            **rate,
            **deepcopy(line),
            "signature": line_signature(line),
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


def group_details(
    original_details: list[dict[str, Any]],
    corrected_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    original: dict[
        tuple[str, bool, bool, bool],
        dict[str, Any],
    ] = defaultdict(
        lambda: {
            "revenue_cents": 0,
            "tax_cents": 0,
            "reference": None,
        }
    )
    corrected: dict[
        tuple[str, bool, bool, bool],
        dict[str, Any],
    ] = defaultdict(
        lambda: {
            "revenue_cents": 0,
            "tax_cents": 0,
            "reference": None,
        }
    )

    for detail in original_details:
        bucket = original[detail["signature"]]
        bucket["revenue_cents"] += detail[
            "amount_cents"
        ]
        bucket["tax_cents"] += detail["tax_cents"]
        bucket["reference"] = detail

    for detail in corrected_details:
        bucket = corrected[detail["signature"]]
        bucket["revenue_cents"] += detail[
            "amount_cents"
        ]
        bucket["tax_cents"] += detail["tax_cents"]
        bucket["reference"] = detail

    result: list[dict[str, Any]] = []

    for signature in sorted(
        set(original) | set(corrected)
    ):
        original_bucket = original.get(
            signature,
            {
                "revenue_cents": 0,
                "tax_cents": 0,
                "reference": None,
            },
        )
        corrected_bucket = corrected.get(
            signature,
            {
                "revenue_cents": 0,
                "tax_cents": 0,
                "reference": None,
            },
        )
        reference = (
            corrected_bucket["reference"]
            or original_bucket["reference"]
        )

        result.append({
            "category": "|".join(
                [
                    signature[0],
                    "PIS" if signature[1] else "",
                    "COFINS" if signature[2] else "",
                    "ICMS_ST" if signature[3] else "",
                ]
            ),
            "category_label": reference["line_label"],
            "original_revenue_cents": original_bucket[
                "revenue_cents"
            ],
            "corrected_revenue_cents": corrected_bucket[
                "revenue_cents"
            ],
            "original_tax_cents": original_bucket[
                "tax_cents"
            ],
            "corrected_tax_cents": corrected_bucket[
                "tax_cents"
            ],
            "difference_cents": (
                corrected_bucket["tax_cents"]
                - original_bucket["tax_cents"]
            ),
            "original_annex": (
                original_bucket["reference"]["annex"]
                if original_bucket["reference"]
                else None
            ),
            "corrected_annex": (
                corrected_bucket["reference"]["annex"]
                if corrected_bucket["reference"]
                else None
            ),
            "original_rate": (
                original_bucket["reference"][
                    "applicable_rate"
                ]
                if original_bucket["reference"]
                else "0"
            ),
            "corrected_rate": (
                corrected_bucket["reference"][
                    "applicable_rate"
                ]
                if corrected_bucket["reference"]
                else "0"
            ),
            "excluded_components": reference[
                "excluded_components"
            ],
            "original_factor_r": (
                original_bucket["reference"].get(
                    "factor_r"
                )
                if original_bucket["reference"]
                else None
            ),
            "corrected_factor_r": (
                corrected_bucket["reference"].get(
                    "factor_r"
                )
                if corrected_bucket["reference"]
                else None
            ),
        })

    return result


def build_tax_setup(
    pgdas_documents: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    calculation_end_competence: str | None,
    full_reflection_end_competence: str | None,
    future_pending_competences: list[str] | None,
    scenario: str,
    saved_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeline = build_revenue_timeline(
        pgdas_documents
    )
    corrections = corrections_from_confirmations(
        confirmations
    )

    if not corrections:
        return {
            "scenario": scenario,
            "profile_version": PROFILE_CODE,
            "months": [],
            "saved_profile": (
                saved_profile
                if saved_profile
                and saved_profile.get("version")
                == PROFILE_CODE
                else None
            ),
            "future_pending_competences": [],
            "description": (
                "O cenário não possui receita adicional "
                "para calcular."
            ),
        }

    first_index = min(corrections)
    computed_full_last = max(corrections) + 12
    full_last_index = (
        month_index(full_reflection_end_competence)
        if full_reflection_end_competence
        else computed_full_last
    )
    last_index = (
        min(
            full_last_index,
            month_index(calculation_end_competence),
        )
        if calculation_end_competence
        else full_last_index
    )
    months: list[dict[str, Any]] = []

    for target_index in range(
        first_index,
        last_index + 1,
    ):
        competence = competence_from_index(
            target_index
        )
        timeline_row = timeline.get(target_index)

        if timeline_row is None:
            months.append({
                "competence": competence,
                "available": False,
                "original_revenue_cents": None,
                "additional_revenue_cents": int(
                    corrections.get(
                        target_index,
                        {"increment_cents": 0},
                    )["increment_cents"]
                ),
                "corrected_revenue_cents": None,
                "source": None,
            })
            continue

        original = int(
            timeline_row["revenue_cents"]
        )
        additional = int(
            corrections.get(
                target_index,
                {"increment_cents": 0},
            )["increment_cents"]
        )
        months.append({
            "competence": competence,
            "available": True,
            "original_revenue_cents": original,
            "additional_revenue_cents": additional,
            "corrected_revenue_cents": (
                original + additional
            ),
            "source": timeline_row.get("source"),
            "source_file": timeline_row.get(
                "source_file",
                "",
            ),
        })

    compatible_profile = (
        saved_profile
        if saved_profile
        and saved_profile.get("version")
        == PROFILE_CODE
        else None
    )

    return {
        "scenario": scenario,
        "profile_version": PROFILE_CODE,
        "first_competence": competence_from_index(
            first_index
        ),
        "calculation_end_competence": (
            competence_from_index(last_index)
        ),
        "full_reflection_end_competence": (
            competence_from_index(full_last_index)
        ),
        "future_pending_competences": (
            future_pending_competences or []
        ),
        "months": months,
        "saved_profile": compatible_profile,
        "description": (
            "Classifique a receita original e a receita "
            "adicional de cada competência."
        ),
    }


def calculate_revenue_line_reflections(
    pgdas_documents: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    profile: dict[str, Any],
    calculation_end_competence: str | None = None,
    full_reflection_end_competence: str | None = None,
    future_pending_competences: list[str] | None = None,
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> dict[str, Any]:
    options = normalize_options(profile)
    timeline = build_revenue_timeline(
        pgdas_documents
    )
    corrections = corrections_from_confirmations(
        confirmations
    )

    if not corrections:
        return {
            "configuration": {
                "annex": "MIXED",
                "profile": PROFILE_CODE,
                "scenario": scenario,
                "period_support": "01/2018_TO_12/2026",
                "options": options,
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
                "Nenhuma exposição adicional de receita "
                "foi identificada."
            ],
        }

    first_index = min(corrections)
    computed_full_last = max(corrections) + 12
    full_last_index = (
        month_index(full_reflection_end_competence)
        if full_reflection_end_competence
        else computed_full_last
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

    allocations = normalize_monthly_allocations(
        profile,
        timeline,
        corrections,
        first_index,
        last_index,
        options,
    )
    payroll_by_index = normalize_factor_r_payroll(
        profile
    )

    hidden_timeline: list[dict[str, Any]] = []
    visible_impacts: list[dict[str, Any]] = []
    missing_months: list[dict[str, Any]] = []
    unsupported_months: list[str] = []
    factor_r_decisions: list[dict[str, Any]] = []
    direct_total = 0
    reflection_total = 0

    for target_index in range(
        first_index,
        last_index + 1,
    ):
        competence = competence_from_index(
            target_index
        )

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
                "missing_competences": sorted(
                    set(missing)
                ),
            })
            continue

        allocation = allocations[target_index]
        original_lines = allocation[
            "original_lines"
        ]
        additional_lines = allocation[
            "additional_lines"
        ]
        corrected_lines = (
            deepcopy(original_lines)
            + deepcopy(additional_lines)
        )

        original_revenue = timeline[target_index][
            "revenue_cents"
        ]
        correction = int(
            corrections.get(
                target_index,
                {"increment_cents": 0},
            )["increment_cents"]
        )
        corrected_revenue = (
            original_revenue + correction
        )
        original_rbt12 = sum(
            timeline[index]["revenue_cents"]
            for index in required_indexes
        )
        corrected_rbt12 = sum(
            timeline[index]["revenue_cents"]
            + int(
                corrections.get(
                    index,
                    {"increment_cents": 0},
                )["increment_cents"]
            )
            for index in required_indexes
        )
        payroll = payroll_by_index.get(
            target_index
        )

        original_tax = calculate_line_group_tax(
            original_lines,
            original_rbt12,
            competence,
            payroll,
        )
        corrected_tax = calculate_line_group_tax(
            corrected_lines,
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

        if (
            is_corrected_competence
            and has_rbt12_reflection
        ):
            classification = (
                "CORRECTED_AND_REFLECTION"
            )
        elif is_corrected_competence:
            classification = (
                "CORRECTED_COMPETENCE"
            )
        elif has_rbt12_reflection:
            classification = "RBT12_REFLECTION"
        else:
            classification = "NO_EFFECT"

        details = (
            original_tax["details"]
            + corrected_tax["details"]
        )

        for detail in details:
            factor_r = detail.get("factor_r")

            if not factor_r:
                continue

            decision = {
                "competence": competence,
                "annex": factor_r["annex"],
                "factor_r": factor_r["factor_r"],
                "payroll_12m_cents": factor_r[
                    "payroll_12m_cents"
                ],
                "rbt12_cents": factor_r[
                    "rbt12_cents"
                ],
                "threshold": decimal_text(
                    FACTOR_R_THRESHOLD
                ),
            }

            if decision not in factor_r_decisions:
                factor_r_decisions.append(
                    decision
                )

        row = {
            "competence": competence,
            "classification": classification,
            "original_revenue_cents": (
                original_revenue
            ),
            "revenue_increment_cents": correction,
            "corrected_revenue_cents": (
                corrected_revenue
            ),
            "original_rbt12_cents": original_rbt12,
            "corrected_rbt12_cents": (
                corrected_rbt12
            ),
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
            "segments": group_details(
                original_tax["details"],
                corrected_tax["details"],
            ),
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
            "Cada competência foi calculada com as linhas "
            "de receita classificadas pelo contador."
        ),
        (
            "A marcação de PIS/Cofins monofásicos depende "
            "da validação dos produtos e das operações."
        ),
        (
            "ICMS-ST deve ser marcado apenas quando a "
            "empresa estiver na condição de substituída "
            "ou houver antecipação com encerramento."
        ),
    ]

    if factor_r_decisions:
        warnings.append(
            "O Fator R foi calculado com a FS12 "
            "informada em cada competência utilizada."
        )

    if missing_months:
        warnings.append(
            "Existem meses sem dados suficientes para "
            "concluir todos os reflexos."
        )

    if future_pending_competences:
        warnings.append(
            "O resultado é parcial até "
            f"{competence_from_index(last_index)}. "
            "Os meses futuros serão incorporados quando "
            "os respectivos PGDAS forem transmitidos."
        )

    if unsupported_months:
        warnings.append(
            "Meses de 2027 ou posteriores permanecem "
            "bloqueados nesta versão."
        )

    return {
        "configuration": {
            "annex": "MIXED",
            "profile": PROFILE_CODE,
            "scenario": scenario,
            "period_support": "01/2018_TO_12/2026",
            "options": options,
        },
        "summary": {
            "corrected_competence_total_cents": (
                direct_total
            ),
            "reflection_total_cents": (
                reflection_total
            ),
            "estimated_total_cents": (
                direct_total + reflection_total
            ),
            "impacted_month_count": len(
                visible_impacts
            ),
            "missing_month_count": len(
                missing_months
            ),
            "unsupported_month_count": len(
                unsupported_months
            ),
            "calculation_end_competence": (
                competence_from_index(last_index)
            ),
            "full_reflection_end_competence": (
                competence_from_index(
                    full_last_index
                )
            ),
            "future_pending_count": len(
                future_pending_competences
            ),
            "is_partial": bool(
                future_pending_competences
            ),
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
