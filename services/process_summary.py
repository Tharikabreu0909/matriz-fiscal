from __future__ import annotations

from typing import Any


TYPE_01_LABEL = "SPED/LFE × movimentação de cartão"
TYPE_17_LABEL = "PGDAS × faturamento fiscal detectado"


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
        reviewed.get(item["competence"], item)
        for item in analysis_result.get("analyses", [])
    ]


def row_status(
    analysis: dict[str, Any],
    study_required: bool,
    has_tax_exposure: bool,
    crossing_type: str,
) -> str:
    if analysis.get("requires_review"):
        return "SOURCE_REVIEW"

    if study_required:
        return "ACCOUNTING_STUDY"

    if crossing_type == "01" and not has_tax_exposure:
        return "ANCILLARY_ONLY"

    if has_tax_exposure:
        return "ACTION_DEFINED"

    return "NO_FINANCIAL_EXPOSURE"


def competence_status(
    analysis: dict[str, Any],
    regularization_status: str,
    has_tax_exposure: bool,
    has_ancillary_divergence: bool,
) -> str:
    if analysis.get("requires_review"):
        return "SOURCE_REVIEW"

    if regularization_status == "PENDING_ACCOUNTING_STUDY":
        return "ACCOUNTING_STUDY"

    if regularization_status == "VALIDATED":
        return "STUDY_VALIDATED"

    if has_tax_exposure:
        return "ACTION_DEFINED"

    if has_ancillary_divergence:
        return "ANCILLARY_ONLY"

    return "NO_FINANCIAL_EXPOSURE"


def next_action(status: str) -> str:
    labels = {
        "SOURCE_REVIEW": "Revisar conflito entre fontes",
        "ACCOUNTING_STUDY": "Concluir estudo contábil",
        "STUDY_VALIDATED": "Aplicar valores validados",
        "ACTION_DEFINED": "Avaliar PGDAS e documentos",
        "ANCILLARY_ONLY": "Conferir SPED/LFE",
        "NO_FINANCIAL_EXPOSURE": "Sem ação financeira",
    }
    return labels.get(status, "Analisar competência")


def build_process_summary(
    analysis_result: dict[str, Any],
    stored_confirmations: list[dict[str, Any]] | None = None,
    tax_result: dict[str, Any] | None = None,
    legal_charges: dict[str, Any] | None = None,
    regularization_result: dict[str, Any] | None = None,
    validated_tax_result: dict[str, Any] | None = None,
    validated_legal_charges: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if regularization_result is not None:
        analyses = regularization_result.get("analyses", [])
        regularization_summary = regularization_result.get(
            "summary",
            {},
        )
    else:
        analyses = effective_analyses(
            analysis_result,
            stored_confirmations,
        )
        regularization_summary = {
            "study_required_count": 0,
            "study_validated_count": 0,
            "study_pending_count": 0,
            "validated_scenario_ready": False,
            "validated_additional_revenue_cents": 0,
            "additional_revenue_reduction_cents": 0,
        }

    rows: list[dict[str, Any]] = []
    competences: list[dict[str, Any]] = []
    exposure_competences: set[str] = set()
    ancillary_only_competences: set[str] = set()
    study_competences: set[str] = set()
    source_review_competences: set[str] = set()
    additional_revenue_total = 0

    for analysis in analyses:
        competence = analysis["competence"]
        segregation = analysis.get("segregation", {})
        type_01 = segregation.get("type_01", {})
        type_17 = segregation.get("type_17", {})
        study = segregation.get("accounting_study", {})
        regularization = analysis.get("regularization", {})
        study_required = bool(study.get("required"))
        type_17_exposure = int(
            type_17.get("simulation_increment_cents") or 0
        )
        type_01_divergence = int(
            type_01.get("minimum_gap_cents")
            or type_01.get("document_divergence_cents")
            or 0
        )
        has_tax_exposure = type_17_exposure > 0
        has_ancillary_divergence = type_01_divergence > 0
        competence_rows: list[dict[str, Any]] = []

        if has_tax_exposure:
            exposure_competences.add(competence)
            additional_revenue_total += type_17_exposure

        if study_required:
            study_competences.add(competence)

        if analysis.get("requires_review"):
            source_review_competences.add(competence)

        validated_status = regularization.get(
            "status",
            (
                "PENDING_ACCOUNTING_STUDY"
                if study_required
                else "NOT_REQUIRED"
            ),
        )

        if type_01.get("present"):
            if has_ancillary_divergence and not has_tax_exposure:
                ancillary_only_competences.add(competence)

            row = {
                "competence": competence,
                "crossing_type": "01",
                "crossing_label": TYPE_01_LABEL,
                "crossing_detail": (
                    "Compara o faturamento escriturado no livro "
                    "com a movimentação de cartão detectada."
                ),
                "informed_cents": type_01.get("informed_cents"),
                "considered_cents": type_01.get(
                    "minimum_detected_cents"
                ),
                "divergence_cents": type_01_divergence,
                "validated_cents": regularization.get(
                    "validated_sped_lfe_revenue_cents"
                ),
                "regularization_status": validated_status,
                "status": row_status(
                    analysis,
                    study_required,
                    has_tax_exposure,
                    "01",
                ),
                "instruction": (
                    "Conferir e reconstruir o SPED/LFE. "
                    "O valor final depende dos documentos fiscais "
                    "válidos."
                ),
                "instruction_code": "RECONSTRUCT_SPED_LFE",
            }
            rows.append(row)
            competence_rows.append(row)

        if type_17.get("present"):
            simulation_target = type_17.get(
                "simulation_target_cents"
            )
            row = {
                "competence": competence,
                "crossing_type": "17",
                "crossing_label": TYPE_17_LABEL,
                "crossing_detail": (
                    "Compara o PGDAS com o maior faturamento "
                    "detectado entre cartão, documentos fiscais "
                    "e SPED/LFE."
                ),
                "informed_cents": (
                    type_17.get("pgdas_imported_cents")
                    or type_17.get("malha_informed_cents")
                ),
                "considered_cents": type_17.get(
                    "considered_cents"
                ),
                "divergence_cents": type_17_exposure,
                "validated_cents": regularization.get(
                    "validated_pgdas_revenue_cents"
                ),
                "validated_increment_cents": regularization.get(
                    "validated_pgdas_increment_cents"
                ),
                "regularization_status": validated_status,
                "status": row_status(
                    analysis,
                    study_required,
                    has_tax_exposure,
                    "17",
                ),
                "instruction": (
                    "Usar o valor fiscal apontado no cenário de "
                    "exposição e validar a composição dos documentos "
                    "antes da retificação definitiva."
                    if has_tax_exposure
                    else (
                        "Nenhum acréscimo potencial foi identificado "
                        "no PGDAS."
                    )
                ),
                "instruction_code": (
                    "VALIDATE_DOCUMENTS_AND_EVALUATE_PGDAS"
                    if has_tax_exposure
                    else "NO_PGDAS_INCREMENT"
                ),
                "simulation_target_cents": simulation_target,
            }
            rows.append(row)
            competence_rows.append(row)

        grouped_status = competence_status(
            analysis=analysis,
            regularization_status=validated_status,
            has_tax_exposure=has_tax_exposure,
            has_ancillary_divergence=has_ancillary_divergence,
        )

        # Quando existem os dois tipos, a divergência tributária do
        # Tipo 17 é a principal. O Tipo 01 continua visível nos detalhes.
        primary_divergence = (
            type_17_exposure
            if type_17_exposure > 0
            else type_01_divergence
        )

        competences.append({
            "competence": competence,
            "types": analysis.get("types", []),
            "status": grouped_status,
            "next_action": next_action(grouped_status),
            "primary_divergence_cents": primary_divergence,
            "additional_revenue_cents": type_17_exposure,
            "study_required": study_required,
            "regularization_status": validated_status,
            "crossings": competence_rows,
        })

    exposure_tax_summary = (tax_result or {}).get("summary", {})
    exposure_charge_summary = (
        legal_charges or {}
    ).get("summary", {})
    validated_tax_summary = (
        validated_tax_result or {}
    ).get("summary", {})
    validated_charge_summary = (
        validated_legal_charges or {}
    ).get("summary", {})

    direct_tax = int(
        exposure_tax_summary.get(
            "corrected_competence_total_cents",
            0,
        )
        or 0
    )
    reflection_tax = int(
        exposure_tax_summary.get("reflection_total_cents", 0)
        or 0
    )
    principal = int(
        exposure_charge_summary.get(
            "principal_cents",
            direct_tax + reflection_tax,
        )
        or 0
    )
    fine = int(
        exposure_charge_summary.get("fine_cents", 0) or 0
    )
    interest = int(
        exposure_charge_summary.get("interest_cents", 0) or 0
    )
    updated_total = int(
        exposure_charge_summary.get("total_cents", principal)
        or 0
    )

    validated_direct = int(
        validated_tax_summary.get(
            "corrected_competence_total_cents",
            0,
        )
        or 0
    )
    validated_reflection = int(
        validated_tax_summary.get("reflection_total_cents", 0)
        or 0
    )
    validated_principal = int(
        validated_charge_summary.get(
            "principal_cents",
            validated_direct + validated_reflection,
        )
        or 0
    )
    validated_fine = int(
        validated_charge_summary.get("fine_cents", 0) or 0
    )
    validated_interest = int(
        validated_charge_summary.get("interest_cents", 0) or 0
    )
    validated_total = int(
        validated_charge_summary.get(
            "total_cents",
            validated_principal,
        )
        or 0
    )

    sort_key = lambda item: (
        int(item["competence"].split("/")[1]),
        int(item["competence"].split("/")[0]),
    )
    rows.sort(
        key=lambda item: (
            *sort_key(item),
            item["crossing_type"],
        )
    )
    competences.sort(key=sort_key)

    action_competence_count = sum(
        item["status"] != "NO_FINANCIAL_EXPOSURE"
        for item in competences
    )

    return {
        "stage": {
            "analysis_complete": (
                analysis_result.get("summary", {})
                .get("awaiting_pgdas_count", 0)
                == 0
            ),
            "tax_calculated": tax_result is not None,
            "legal_charges_calculated": legal_charges is not None,
            "validated_tax_calculated": (
                validated_tax_result is not None
            ),
            "validated_legal_charges_calculated": (
                validated_legal_charges is not None
            ),
        },
        "metrics": {
            "competence_count": len(analyses),
            "action_competence_count": action_competence_count,
            "exposure_competence_count": len(
                exposure_competences
            ),
            "ancillary_only_competence_count": len(
                ancillary_only_competences
            ),
            "accounting_study_count": len(study_competences),
            "source_review_count": len(
                source_review_competences
            ),
            "study_validated_count": regularization_summary.get(
                "study_validated_count",
                0,
            ),
            "study_pending_count": regularization_summary.get(
                "study_pending_count",
                0,
            ),
            "validated_scenario_ready": regularization_summary.get(
                "validated_scenario_ready",
                False,
            ),
        },
        "financial": {
            "additional_revenue_cents": additional_revenue_total,
            "direct_tax_cents": direct_tax,
            "reflection_tax_cents": reflection_tax,
            "principal_cents": principal,
            "fine_cents": fine,
            "interest_cents": interest,
            "charges_cents": fine + interest,
            "updated_total_cents": updated_total,
        },
        "validated_financial": {
            "additional_revenue_cents": (
                regularization_summary.get(
                    "validated_additional_revenue_cents",
                    0,
                )
            ),
            "direct_tax_cents": validated_direct,
            "reflection_tax_cents": validated_reflection,
            "principal_cents": validated_principal,
            "fine_cents": validated_fine,
            "interest_cents": validated_interest,
            "charges_cents": (
                validated_fine + validated_interest
            ),
            "updated_total_cents": validated_total,
            "reduction_from_exposure_cents": (
                updated_total - validated_total
                if (
                    validated_tax_result is not None
                    or validated_legal_charges is not None
                )
                else regularization_summary.get(
                    "additional_revenue_reduction_cents",
                    0,
                )
            ),
        },
        # Mantido para compatibilidade com integrações existentes.
        "rows": rows,
        # Visão principal: uma entrada por competência.
        "competences": competences,
    }
