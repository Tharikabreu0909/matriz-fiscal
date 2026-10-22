from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_revenue_index(
    pgdas_documents: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Produz uma única linha de receitas declaradas.

    O valor do próprio PA tem prioridade sobre o histórico de outro
    documento PGDAS-D.
    """
    index: dict[str, dict[str, Any]] = {}

    for pgdas in pgdas_documents:
        source_file = (
            pgdas.get("source_document", {})
            .get("file_name", "")
        )
        assessment = pgdas.get("assessment", {})

        for row in assessment.get("previous_revenues", []):
            competence = row["competence"]

            if competence not in index:
                index[competence] = {
                    "competence": competence,
                    "declared_revenue_cents": row["total_cents"],
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
            index[period] = {
                "competence": period,
                "declared_revenue_cents": current_revenue,
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


def accounting_study_model(
    type_01_result: dict[str, Any] | None,
    type_17_result: dict[str, Any] | None,
    pgdas_increment_cents: int,
    cross_type_comparison: str,
) -> dict[str, Any]:
    reasons: list[str] = []

    if type_01_result:
        if type_01_result["sped_lfe_informed_cents"] == 0:
            reasons.append("SPED_LFE_ZERO_OR_NOT_TRANSMITTED")

        if (
            type_01_result["considered_cents"]
            > type_01_result["sped_lfe_informed_cents"]
        ):
            reasons.append(
                "SPED_LFE_BELOW_MINIMUM_DETECTED"
            )

    if type_17_result and pgdas_increment_cents > 0:
        reasons.append("FISCAL_VALUE_ABOVE_PGDAS")

    if cross_type_comparison == "DIFFERENT_CONSIDERED_VALUES":
        reasons.append("CROSSINGS_USE_DIFFERENT_VALUES")

    required = bool(reasons)

    return {
        "required": required,
        "status": (
            "PENDING_ACCOUNTING_STUDY"
            if required
            else "NOT_REQUIRED"
        ),
        "reason_codes": reasons,
        "questions": (
            [
                (
                    "Os documentos fiscais que compõem o valor "
                    "considerado pertencem realmente a esta competência?"
                ),
                (
                    "Existe nota extemporânea, complementar, cancelada, "
                    "devolução, duplicidade ou documento de outro período?"
                ),
                (
                    "O valor do cartão já está contido nas vendas "
                    "documentadas ou representa operações diferentes?"
                ),
                (
                    "Qual receita deve constar definitivamente no "
                    "PGDAS e na escrituração?"
                ),
            ]
            if required
            else []
        ),
        "blocks_exposure_simulation": False,
        "blocks_final_regularization_instruction": required,
    }


def build_segregation(
    evidence: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    type_01_result = evidence.get("type_01")
    type_17_result = evidence.get("type_17")
    pgdas_imported = evidence.get("pgdas_imported")

    type_01_section = {
        "present": type_01_result is not None,
        "purpose": "ANCILLARY_OBLIGATION",
        "generates_tax": False,
        "informed_cents": (
            type_01_result["sped_lfe_informed_cents"]
            if type_01_result
            else None
        ),
        "considered_cents": (
            type_01_result["considered_cents"]
            if type_01_result
            else None
        ),
        "minimum_detected_cents": (
            type_01_result["considered_cents"]
            if type_01_result
            else None
        ),
        "document_divergence_cents": (
            type_01_result["document_divergence_cents"]
            if type_01_result
            else None
        ),
        "minimum_gap_cents": (
            recommendation["sped_increment_cents"]
        ),
        "recommended_increment_cents": (
            recommendation["sped_increment_cents"]
        ),
        "recommended_target_cents": None,
        "regularization_target_status": (
            "REQUIRES_DOCUMENT_RECONSTRUCTION"
            if (
                type_01_result
                and recommendation["sped_increment_cents"] > 0
            )
            else "NOT_APPLICABLE"
        ),
        "interpretation": (
            "MINIMUM_DIVERGENCE_NOT_FINAL_BOOK_VALUE"
            if type_01_result
            else "NOT_APPLICABLE"
        ),
    }

    type_17_section = {
        "present": type_17_result is not None,
        "purpose": "PGDAS_FISCAL_EXPOSURE",
        "generates_tax": (
            recommendation[
                "simulation_pgdas_increment_cents"
            ] > 0
        ),
        "malha_informed_cents": (
            type_17_result["malha_pgdas_informed_cents"]
            if type_17_result
            else None
        ),
        "pgdas_imported_cents": (
            pgdas_imported["declared_revenue_cents"]
            if pgdas_imported
            else None
        ),
        "considered_cents": (
            type_17_result["considered_cents"]
            if type_17_result
            else None
        ),
        "document_divergence_cents": (
            type_17_result["document_divergence_cents"]
            if type_17_result
            else None
        ),
        "simulation_increment_cents": (
            recommendation[
                "simulation_pgdas_increment_cents"
            ]
        ),
        "simulation_target_cents": (
            recommendation[
                "simulation_pgdas_revenue_cents"
            ]
        ),
        "recommended_increment_cents": (
            recommendation[
                "simulation_pgdas_increment_cents"
            ]
        ),
        "recommended_target_cents": None,
        "regularization_target_cents": (
            recommendation[
                "validated_pgdas_revenue_cents"
            ]
        ),
        "regularization_target_status": (
            "PENDING_ACCOUNTING_STUDY"
            if (
                type_17_result
                and recommendation[
                    "simulation_pgdas_increment_cents"
                ] > 0
                and recommendation[
                    "validated_pgdas_revenue_cents"
                ] is None
            )
            else "NOT_REQUIRED_OR_VALIDATED"
        ),
    }

    cross_type_comparison = "NOT_APPLICABLE"

    if type_01_result and type_17_result:
        cross_type_comparison = (
            "SAME_CONSIDERED_VALUE"
            if (
                type_01_result["considered_cents"]
                == type_17_result["considered_cents"]
            )
            else "DIFFERENT_CONSIDERED_VALUES"
        )

    study = accounting_study_model(
        type_01_result,
        type_17_result,
        recommendation[
            "simulation_pgdas_increment_cents"
        ],
        cross_type_comparison,
    )

    return {
        "type_01": type_01_section,
        "type_17": type_17_section,
        "cross_type_comparison": cross_type_comparison,
        "accounting_study": study,
        "consolidated": {
            "sped_lfe_target_cents": None,
            "pgdas_target_cents": (
                recommendation[
                    "validated_pgdas_revenue_cents"
                ]
            ),
            "simulation_revenue_cents": (
                recommendation[
                    "simulation_pgdas_revenue_cents"
                ]
            ),
            "simulation_tax_base_increment_cents": (
                recommendation[
                    "simulation_pgdas_increment_cents"
                ]
            ),
            # Campo mantido por compatibilidade com o motor.
            "tax_base_increment_cents": (
                recommendation[
                    "simulation_pgdas_increment_cents"
                ]
            ),
            "combined_divergence_cents": None,
            "regularization_status": study["status"],
            "calculation_rule": (
                "USE_TYPE_17_FOR_EXPOSURE_"
                "DO_NOT_INFER_FINAL_SPED_TARGET"
            ),
            "tax_source": "TYPE_17_ONLY",
            "scenario": "CONSERVATIVE_FISCAL_EXPOSURE",
        },
    }


def analyze_competence(
    month: dict[str, Any],
    revenue_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    competence = month["competence"]
    notices = unique_notices_by_type(month)
    warnings: list[str] = []
    actions: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}

    recommendation: dict[str, Any] = {
        # Compatibilidade: representa a diferença mínima do Tipo 01.
        "sped_increment_cents": 0,
        # Compatibilidade: representa a exposição do Tipo 17.
        "pgdas_increment_cents": 0,
        "corrected_pgdas_revenue_cents": None,
        # Campos novos e semanticamente corretos.
        "simulation_pgdas_increment_cents": 0,
        "simulation_pgdas_revenue_cents": None,
        "validated_pgdas_revenue_cents": None,
        "calculate_direct_tax": False,
        "calculate_rbt12_reflections": False,
        "calculation_basis": (
            "CONSERVATIVE_FISCAL_EXPOSURE"
        ),
    }

    type_01 = notices.get("01", [])

    if len(type_01) > 1:
        warnings.append(
            "Há mais de um aviso tipo 01 com valores diferentes. "
            "Revise as linhas antes de definir a escrituração."
        )

    if type_01:
        notice = type_01[0]
        informed = notice["informed_cents"]
        considered = notice["considered_cents"]
        minimum_gap = max(0, considered - informed)

        evidence["type_01"] = {
            "sped_lfe_informed_cents": informed,
            "considered_cents": considered,
            "document_divergence_cents": (
                notice["divergence_cents"]
            ),
        }
        recommendation["sped_increment_cents"] = minimum_gap

        if minimum_gap > 0:
            actions.append({
                "action": "RECONSTRUCT_SPED_LFE",
                "minimum_detected_cents": considered,
                "minimum_gap_cents": minimum_gap,
            })

    type_17 = notices.get("17", [])
    declared_source = revenue_index.get(competence)

    if len(type_17) > 1:
        warnings.append(
            "Há mais de um aviso tipo 17 com valores diferentes. "
            "Revise as fontes antes de definir o cenário."
        )

    source_consistency = "NOT_APPLICABLE"

    if type_17:
        notice = type_17[0]
        malha_informed = notice["informed_cents"]
        considered = notice["considered_cents"]

        evidence["type_17"] = {
            "malha_pgdas_informed_cents": malha_informed,
            "considered_cents": considered,
            "document_divergence_cents": (
                notice["divergence_cents"]
            ),
        }

        if declared_source is None:
            segregation = build_segregation(
                evidence,
                recommendation,
            )

            return {
                "competence": competence,
                "types": month.get("types", []),
                "status": "AWAITING_PGDAS",
                "confidence": "UNAVAILABLE",
                "source_consistency": "UNKNOWN",
                "evidence": evidence,
                "segregation": segregation,
                "recommendation": recommendation,
                "actions": actions,
                "warnings": warnings,
                "explanation": (
                    "Ainda não há receita declarada importada para "
                    "esta competência."
                ),
                "requires_review": False,
                "requires_confirmation": False,
                "automation": {
                    "mode": "WAITING_FOR_DATA",
                    "decision_source": "NONE",
                },
            }

        declared = declared_source[
            "declared_revenue_cents"
        ]
        simulation_target = max(
            declared,
            considered,
        )
        simulation_increment = max(
            0,
            simulation_target - declared,
        )

        evidence["pgdas_imported"] = {
            **declared_source,
        }

        source_consistency = (
            "MATCH"
            if declared == malha_informed
            else "DIFFERENT_FROM_MALHA"
        )

        if source_consistency == "DIFFERENT_FROM_MALHA":
            warnings.append(
                "A receita do PGDAS importado é diferente da receita "
                "informada na malha. Isso pode indicar retificação "
                "posterior ou arquivo de outra versão da apuração."
            )

        recommendation[
            "simulation_pgdas_increment_cents"
        ] = simulation_increment
        recommendation[
            "simulation_pgdas_revenue_cents"
        ] = simulation_target

        # Aliases mantidos para os módulos tributários existentes.
        recommendation[
            "pgdas_increment_cents"
        ] = simulation_increment
        recommendation[
            "corrected_pgdas_revenue_cents"
        ] = simulation_target
        recommendation[
            "calculate_direct_tax"
        ] = simulation_increment > 0
        recommendation[
            "calculate_rbt12_reflections"
        ] = simulation_increment > 0

        if simulation_increment > 0:
            actions.extend([
                {
                    "action": (
                        "SIMULATE_PGDAS_EXPOSURE"
                    ),
                    "amount_cents": simulation_increment,
                    "simulation_target_cents": (
                        simulation_target
                    ),
                },
                {
                    "action": "CALCULATE_DIRECT_TAX",
                },
                {
                    "action": (
                        "CALCULATE_RBT12_REFLECTIONS"
                    ),
                },
                {
                    "action": (
                        "VALIDATE_DOCUMENTS_BEFORE_"
                        "REGULARIZATION"
                    ),
                },
            ])

    segregation = build_segregation(
        evidence,
        recommendation,
    )

    if warnings:
        status = "REVIEW_REQUIRED"
        confidence = "LOW_FOR_SOURCE_SELECTION"
        explanation = (
            "O sistema encontrou conflito entre as fontes. "
            "Revise qual versão da receita deve alimentar a simulação."
        )
    elif actions:
        status = "AUTO_ANALYZED"
        confidence = "HIGH_FOR_EXPOSURE"
        explanation = (
            "A exposição fiscal foi calculada automaticamente. "
            "O valor definitivo da regularização depende do estudo "
            "contábil dos documentos."
        )
    else:
        status = "NO_ACTION_REQUIRED"
        confidence = "HIGH"
        explanation = (
            "Análise concluída automaticamente, sem exposição "
            "tributária adicional identificada."
        )

    return {
        "competence": competence,
        "types": month.get("types", []),
        "status": status,
        "confidence": confidence,
        "source_consistency": source_consistency,
        "evidence": evidence,
        "segregation": segregation,
        "recommendation": recommendation,
        "actions": actions,
        "warnings": warnings,
        "explanation": explanation,
        "requires_review": status == "REVIEW_REQUIRED",
        "requires_confirmation": status == "REVIEW_REQUIRED",
        "automation": {
            "mode": (
                "EXCEPTION_REVIEW"
                if status == "REVIEW_REQUIRED"
                else "AUTOMATIC_EXPOSURE_SIMULATION"
            ),
            "decision_source": (
                "ACCOUNTANT_EXCEPTION"
                if status == "REVIEW_REQUIRED"
                else "CHECKFISCAL_ENGINE"
            ),
        },
    }


def analyze_process(
    malha: dict[str, Any],
    pgdas_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    revenue_index = build_revenue_index(
        pgdas_documents
    )

    analyses = [
        analyze_competence(month, revenue_index)
        for month in malha.get("work_months", [])
    ]

    return {
        "summary": {
            "competence_count": len(analyses),
            "auto_analyzed_count": sum(
                item["status"] == "AUTO_ANALYZED"
                for item in analyses
            ),
            "ready_for_confirmation_count": 0,
            "review_required_count": sum(
                item["status"] == "REVIEW_REQUIRED"
                for item in analyses
            ),
            "awaiting_pgdas_count": sum(
                item["status"] == "AWAITING_PGDAS"
                for item in analyses
            ),
            "no_action_count": sum(
                item["status"] == "NO_ACTION_REQUIRED"
                for item in analyses
            ),
            "accounting_study_pending_count": sum(
                item.get("segregation", {})
                .get("accounting_study", {})
                .get("status")
                == "PENDING_ACCOUNTING_STUDY"
                for item in analyses
            ),
        },
        "analyses": analyses,
    }
