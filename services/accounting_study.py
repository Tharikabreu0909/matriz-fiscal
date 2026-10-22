from __future__ import annotations

from copy import deepcopy
from typing import Any


EXPOSURE_SCENARIO = "CONSERVATIVE_FISCAL_EXPOSURE"
VALIDATED_SCENARIO = "VALIDATED_REGULARIZATION"

ALLOWED_REASON_CODES = {
    # Causas mais comuns na rotina dos escritórios.
    "CARD_SALE_WITHOUT_INVOICE",
    "DOCUMENT_NOT_IMPORTED",
    "PGDAS_ENTRY_ERROR",
    "SPED_NOT_SENT_OR_ZERO",
    "REVENUE_WRONG_COMPETENCE",
    "CANCELLED_RETURNED_OR_DUPLICATE",
    "CARD_ALREADY_INCLUDED",
    "MIXED_CAUSES",
    "OTHER",
    # Códigos anteriores preservados por compatibilidade.
    "DOCUMENTS_BELONG_TO_COMPETENCE",
    "EXTEMPORANEOUS_OTHER_COMPETENCE",
    "CANCELLED_OR_RETURNED_DOCUMENT",
    "DUPLICATE_DOCUMENT",
}


class AccountingStudyError(ValueError):
    pass


def effective_analyses(
    analysis_result: dict[str, Any],
    stored_confirmations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    reviewed = {
        item["competence"]: item["analysis"]
        for item in (stored_confirmations or [])
        if item.get("decision") == "CONFIRMED"
    }

    return [
        deepcopy(
            reviewed.get(item["competence"], item)
        )
        for item in analysis_result.get("analyses", [])
    ]


def requirements_for_analysis(
    analysis: dict[str, Any],
) -> dict[str, bool]:
    segregation = analysis.get("segregation", {})
    study = segregation.get("accounting_study", {})
    type_01 = segregation.get("type_01", {})
    type_17 = segregation.get("type_17", {})

    if not study.get("required"):
        return {
            "study_required": False,
            "requires_sped_value": False,
            "requires_pgdas_value": False,
        }

    return {
        "study_required": True,
        "requires_sped_value": bool(
            type_01.get("present")
        ),
        "requires_pgdas_value": bool(
            type_17.get("present")
        ),
    }


def validate_conclusion(
    analysis: dict[str, Any],
    conclusion: dict[str, Any],
) -> None:
    requirements = requirements_for_analysis(analysis)

    if not requirements["study_required"]:
        raise AccountingStudyError(
            "Esta competência não exige conclusão de estudo contábil."
        )

    reason_code = conclusion.get("reason_code", "")

    if reason_code not in ALLOWED_REASON_CODES:
        raise AccountingStudyError(
            "Selecione um motivo válido para a conclusão."
        )

    if (
        reason_code == "OTHER"
        and not conclusion.get("notes", "").strip()
    ):
        raise AccountingStudyError(
            "Descreva o motivo quando selecionar Outros."
        )

    if (
        requirements["requires_sped_value"]
        and conclusion.get(
            "validated_sped_lfe_revenue_cents"
        ) is None
    ):
        raise AccountingStudyError(
            "Informe o valor validado do SPED/LFE."
        )

    if (
        requirements["requires_pgdas_value"]
        and conclusion.get(
            "validated_pgdas_revenue_cents"
        ) is None
    ):
        raise AccountingStudyError(
            "Informe a receita validada do PGDAS."
        )

    for field in (
        "validated_sped_lfe_revenue_cents",
        "validated_pgdas_revenue_cents",
    ):
        value = conclusion.get(field)

        if value is not None and value < 0:
            raise AccountingStudyError(
                "Os valores validados não podem ser negativos."
            )


def enrich_analysis(
    analysis: dict[str, Any],
    conclusion: dict[str, Any] | None,
) -> dict[str, Any]:
    item = deepcopy(analysis)
    segregation = item.setdefault("segregation", {})
    type_01 = segregation.setdefault("type_01", {})
    type_17 = segregation.setdefault("type_17", {})
    study = segregation.setdefault(
        "accounting_study",
        {},
    )
    consolidated = segregation.setdefault(
        "consolidated",
        {},
    )
    requirements = requirements_for_analysis(item)

    imported_pgdas = (
        type_17.get("pgdas_imported_cents")
        if type_17.get("present")
        else None
    )
    exposure_target = type_17.get(
        "simulation_target_cents"
    )
    exposure_increment = int(
        type_17.get("simulation_increment_cents")
        or 0
    )

    if not requirements["study_required"]:
        regularization = {
            "status": "NOT_REQUIRED",
            "study_required": False,
            "requirements": requirements,
            "validated_sped_lfe_revenue_cents": (
                type_01.get("informed_cents")
                if type_01.get("present")
                else None
            ),
            "validated_pgdas_revenue_cents": (
                imported_pgdas
                if type_17.get("present")
                else None
            ),
            "validated_pgdas_increment_cents": 0,
            "reason_code": "",
            "notes": "",
            "exposure_target_cents": exposure_target,
            "exposure_increment_cents": exposure_increment,
            "difference_from_exposure_cents": 0,
        }
    elif conclusion is None:
        regularization = {
            "status": "PENDING_ACCOUNTING_STUDY",
            "study_required": True,
            "requirements": requirements,
            "validated_sped_lfe_revenue_cents": None,
            "validated_pgdas_revenue_cents": None,
            "validated_pgdas_increment_cents": None,
            "reason_code": "",
            "notes": "",
            "exposure_target_cents": exposure_target,
            "exposure_increment_cents": exposure_increment,
            "difference_from_exposure_cents": None,
        }
    else:
        validate_conclusion(item, conclusion)
        validated_pgdas = conclusion.get(
            "validated_pgdas_revenue_cents"
        )
        validated_increment = (
            max(0, validated_pgdas - imported_pgdas)
            if (
                validated_pgdas is not None
                and imported_pgdas is not None
            )
            else 0
        )
        difference_from_exposure = (
            validated_pgdas - exposure_target
            if (
                validated_pgdas is not None
                and exposure_target is not None
            )
            else None
        )

        regularization = {
            "status": "VALIDATED",
            "study_required": True,
            "requirements": requirements,
            "validated_sped_lfe_revenue_cents": (
                conclusion.get(
                    "validated_sped_lfe_revenue_cents"
                )
            ),
            "validated_pgdas_revenue_cents": (
                validated_pgdas
            ),
            "validated_pgdas_increment_cents": (
                validated_increment
            ),
            "reason_code": conclusion.get(
                "reason_code",
                "",
            ),
            "notes": conclusion.get("notes", ""),
            "created_at": conclusion.get("created_at"),
            "updated_at": conclusion.get("updated_at"),
            "exposure_target_cents": exposure_target,
            "exposure_increment_cents": exposure_increment,
            "difference_from_exposure_cents": (
                difference_from_exposure
            ),
        }

    item["regularization"] = regularization

    type_01[
        "validated_target_cents"
    ] = regularization[
        "validated_sped_lfe_revenue_cents"
    ]
    type_17[
        "validated_target_cents"
    ] = regularization[
        "validated_pgdas_revenue_cents"
    ]
    type_17[
        "validated_increment_cents"
    ] = regularization[
        "validated_pgdas_increment_cents"
    ]

    consolidated[
        "validated_sped_lfe_revenue_cents"
    ] = regularization[
        "validated_sped_lfe_revenue_cents"
    ]
    consolidated[
        "validated_pgdas_revenue_cents"
    ] = regularization[
        "validated_pgdas_revenue_cents"
    ]
    consolidated[
        "validated_pgdas_increment_cents"
    ] = regularization[
        "validated_pgdas_increment_cents"
    ]
    consolidated[
        "regularization_status"
    ] = regularization["status"]

    return item


def apply_study_conclusions(
    analysis_result: dict[str, Any],
    stored_confirmations: list[dict[str, Any]] | None,
    conclusions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    conclusion_by_competence = {
        item["competence"]: item
        for item in (conclusions or [])
    }
    analyses = [
        enrich_analysis(
            analysis,
            conclusion_by_competence.get(
                analysis["competence"]
            ),
        )
        for analysis in effective_analyses(
            analysis_result,
            stored_confirmations,
        )
    ]

    required = [
        item
        for item in analyses
        if item["regularization"]["study_required"]
    ]
    validated = [
        item
        for item in required
        if item["regularization"]["status"] == "VALIDATED"
    ]

    exposure_additional_revenue = sum(
        int(
            item.get("regularization", {}).get(
                "exposure_increment_cents"
            )
            or 0
        )
        for item in analyses
    )
    validated_additional_revenue = sum(
        int(
            item.get("regularization", {}).get(
                "validated_pgdas_increment_cents"
            )
            or 0
        )
        for item in analyses
        if item["regularization"]["status"] in {
            "VALIDATED",
            "NOT_REQUIRED",
        }
    )

    return {
        "summary": {
            "study_required_count": len(required),
            "study_validated_count": len(validated),
            "study_pending_count": len(required) - len(validated),
            "validated_scenario_ready": (
                len(required) == len(validated)
            ),
            "exposure_additional_revenue_cents": (
                exposure_additional_revenue
            ),
            "validated_additional_revenue_cents": (
                validated_additional_revenue
            ),
            "additional_revenue_reduction_cents": (
                exposure_additional_revenue
                - validated_additional_revenue
            ),
        },
        "analyses": analyses,
    }


def build_scenario_confirmations(
    regularization_result: dict[str, Any],
    scenario: str,
) -> list[dict[str, Any]]:
    if scenario not in {
        EXPOSURE_SCENARIO,
        VALIDATED_SCENARIO,
    }:
        raise AccountingStudyError(
            "Cenário tributário inválido."
        )

    if (
        scenario == VALIDATED_SCENARIO
        and not regularization_result["summary"][
            "validated_scenario_ready"
        ]
    ):
        raise AccountingStudyError(
            "Conclua todos os estudos contábeis antes de "
            "calcular a regularização validada."
        )

    confirmations: list[dict[str, Any]] = []

    for source in regularization_result["analyses"]:
        analysis = deepcopy(source)
        recommendation = analysis.setdefault(
            "recommendation",
            {},
        )

        if scenario == EXPOSURE_SCENARIO:
            target = recommendation.get(
                "simulation_pgdas_revenue_cents"
            )
            increment = recommendation.get(
                "simulation_pgdas_increment_cents"
            ) or 0
        else:
            regularization = analysis["regularization"]
            target = regularization.get(
                "validated_pgdas_revenue_cents"
            )
            increment = regularization.get(
                "validated_pgdas_increment_cents"
            ) or 0

        recommendation[
            "simulation_pgdas_revenue_cents"
        ] = target
        recommendation[
            "simulation_pgdas_increment_cents"
        ] = increment
        recommendation[
            "corrected_pgdas_revenue_cents"
        ] = target
        recommendation[
            "pgdas_increment_cents"
        ] = increment
        recommendation[
            "calculation_basis"
        ] = scenario

        confirmations.append({
            "competence": analysis["competence"],
            "decision": (
                "VALIDATED_REGULARIZATION"
                if scenario == VALIDATED_SCENARIO
                else "AUTO_APPROVED"
            ),
            "analysis": analysis,
        })

    return confirmations
