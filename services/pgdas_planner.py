from __future__ import annotations

from copy import deepcopy
from datetime import date
import re
from typing import Any

from services.reflection_coverage import (
    latest_normally_due_competence,
)


HISTORY_MONTHS = 24


def normalize_type_code(value: Any) -> str:
    """Normaliza códigos vindos de leitores/bancos antigos (01, 1, 17)."""
    if value is None:
        return ""
    text = str(value).strip()
    match = re.search(r"(?<!\d)(17|0?1)(?!\d)", text)
    if not match:
        return ""
    code = match.group(1)
    return "01" if code in {"1", "01"} else "17"


def normalize_competence(value: Any) -> str:
    """Converte competências e referências datadas para MM/AAAA."""
    if value is None:
        return ""
    text = str(value).strip()
    match = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return f"{month:02d}/{year}" if 1 <= month <= 12 else ""
    match = re.fullmatch(r"\d{1,2}/(\d{1,2})/(\d{4})", text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return f"{month:02d}/{year}" if 1 <= month <= 12 else ""
    match = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        return f"{month:02d}/{year}" if 1 <= month <= 12 else ""
    return ""


def _row_type_code(row: dict[str, Any]) -> str:
    for candidate in (
        row.get("type_code"),
        row.get("type"),
        row.get("type_description"),
        (row.get("source_cells") or {}).get("type"),
    ):
        code = normalize_type_code(candidate)
        if code:
            return code
    return ""


def normalize_malha_data(malha_data: dict[str, Any]) -> dict[str, Any]:
    """Reconcilia competências/tipos com as linhas brutas da malha.

    Protege processos antigos ou dados parcialmente estruturados: a presença
    do Tipo 17 em uma linha bruta não pode desaparecer porque a lista
    agregada ``work_months`` ficou desatualizada ou trouxe o código numérico.
    """
    normalized = deepcopy(malha_data or {})
    raw_rows = normalized.get("raw_rows") or []
    rows_by_competence: dict[str, list[dict[str, Any]]] = {}
    raw_type_codes: set[str] = set()

    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        competence = normalize_competence(row.get("competence"))
        if not competence:
            competence = normalize_competence(row.get("reference"))
        code = _row_type_code(row)
        if code:
            raw_type_codes.add(code)
            row["type_code"] = code
        if competence:
            row["competence"] = competence
            rows_by_competence.setdefault(competence, []).append(row)

    existing_months = normalized.get("work_months") or []
    months_by_competence: dict[str, dict[str, Any]] = {}
    for source_month in existing_months:
        if not isinstance(source_month, dict):
            continue
        month = deepcopy(source_month)
        competence = normalize_competence(month.get("competence"))
        if not competence:
            continue
        month["competence"] = competence
        source_types = month.get("types") or []
        if isinstance(source_types, str):
            source_types = [source_types]
        types = {
            code
            for code in (normalize_type_code(item) for item in source_types)
            if code
        }
        types.update(
            _row_type_code(row)
            for row in rows_by_competence.get(competence, [])
            if _row_type_code(row)
        )
        month["types"] = sorted(types)
        actions = list(month.get("preliminary_actions") or [])
        if "01" in types and "REVIEW_AND_RECTIFY_SPED_LFE" not in actions:
            actions.append("REVIEW_AND_RECTIFY_SPED_LFE")
        if "17" in types and "IMPORT_PGDAS_AND_EVALUATE_TAX" not in actions:
            actions.append("IMPORT_PGDAS_AND_EVALUATE_TAX")
        month["preliminary_actions"] = actions

        rows_for_month = rows_by_competence.get(competence, [])
        if rows_for_month:
            month["raw_row_count"] = len(rows_for_month)
            month["duplicate_count"] = sum(bool(row.get("duplicate")) for row in rows_for_month)
            month["unique_notice_count"] = sum(not bool(row.get("duplicate")) for row in rows_for_month)
            month["raw_row_ids"] = [row.get("id") for row in rows_for_month if row.get("id") is not None]
            notices = list(month.get("notices") or [])
            known = {
                (
                    normalize_type_code(item.get("type_code")),
                    int(item.get("informed_cents", 0) or 0),
                    int(item.get("considered_cents", 0) or 0),
                    int(item.get("divergence_cents", 0) or 0),
                )
                for item in notices
                if isinstance(item, dict)
            }
            for row in rows_for_month:
                if row.get("duplicate"):
                    continue
                notice = {
                    "type_code": _row_type_code(row),
                    "informed_field": row.get("informed_field", ""),
                    "informed_cents": row.get("informed_cents", 0),
                    "considered_cents": row.get("considered_cents", 0),
                    "divergence_cents": row.get("divergence_cents", 0),
                    "duplicate": False,
                }
                key = (
                    notice["type_code"],
                    int(notice["informed_cents"] or 0),
                    int(notice["considered_cents"] or 0),
                    int(notice["divergence_cents"] or 0),
                )
                if notice["type_code"] and key not in known:
                    notices.append(notice)
                    known.add(key)
            month["notices"] = notices
        months_by_competence[competence] = month

    # Se houver linha bruta que não entrou na agregação, adiciona a competência.
    for competence, rows_for_month in rows_by_competence.items():
        if competence in months_by_competence:
            continue
        types = sorted({
            code for code in (_row_type_code(row) for row in rows_for_month) if code
        })
        unique_rows = [row for row in rows_for_month if not row.get("duplicate")]
        notices = [{
            "type_code": _row_type_code(row),
            "informed_field": row.get("informed_field", ""),
            "informed_cents": row.get("informed_cents", 0),
            "considered_cents": row.get("considered_cents", 0),
            "divergence_cents": row.get("divergence_cents", 0),
            "duplicate": False,
        } for row in unique_rows]
        actions = []
        if "01" in types:
            actions.append("REVIEW_AND_RECTIFY_SPED_LFE")
        if "17" in types:
            actions.append("IMPORT_PGDAS_AND_EVALUATE_TAX")
        months_by_competence[competence] = {
            "competence": competence,
            "types": types,
            "raw_row_count": len(rows_for_month),
            "unique_notice_count": len(unique_rows),
            "duplicate_count": len(rows_for_month) - len(unique_rows),
            "raw_row_ids": [row.get("id") for row in rows_for_month if row.get("id") is not None],
            "notices": notices,
            "preliminary_actions": actions,
            "status": "AWAITING_CONFIRMATION",
        }

    work_months = sorted(months_by_competence.values(), key=lambda item: month_index(item["competence"]))
    normalized["work_months"] = work_months

    summary = dict(normalized.get("summary") or {})
    summary["work_month_count"] = len(work_months)
    summary["types_found"] = sorted(
        raw_type_codes
        | {code for month in work_months for code in month.get("types", [])}
    )
    if raw_rows:
        summary["raw_row_count"] = len(raw_rows)
        summary["unique_raw_notice_count"] = sum(not bool(row.get("duplicate")) for row in raw_rows if isinstance(row, dict))
        summary["duplicate_row_count"] = sum(bool(row.get("duplicate")) for row in raw_rows if isinstance(row, dict))
    normalized["summary"] = summary
    return normalized


def month_index(competence: str) -> int:
    month, year = map(int, competence.split("/"))
    return year * 12 + month - 1


def competence_from_index(value: int) -> str:
    year, zero_based_month = divmod(value, 12)
    return f"{zero_based_month + 1:02d}/{year}"


def initial_document_requests(
    malha_competences: list[str],
    type_01_months: list[str],
    type_17_months: list[str],
    history_months: int,
) -> list[dict[str, Any]]:
    """Planeja PGDAS para conferência de toda competência da malha.

    O PGDAS é solicitado também para Tipo 01: ele confirma o que foi
    declarado naquela competência e ajuda a identificar defasagem da malha.
    A presença de Tipo 01, por si só, não gera cálculo tributário; esse cálculo
    continua condicionado à exposição do Tipo 17.

    Um PGDAS mais recente pode cobrir competências anteriores presentes em seu
    histórico. Cada competência-alvo é coberta por pelo menos uma solicitação.
    """
    type_01_set = set(type_01_months)
    type_17_set = set(type_17_months)
    not_covered = {
        month_index(competence): competence
        for competence in malha_competences
    }
    requests: list[dict[str, Any]] = []

    while not_covered:
        requested_index = max(not_covered)
        requested_competence = not_covered[requested_index]
        coverage_start_index = requested_index - history_months
        covered_indexes = sorted(
            index
            for index in not_covered
            if coverage_start_index <= index <= requested_index
        )
        covered_competences = [not_covered[index] for index in covered_indexes]
        covered_type_01 = [item for item in covered_competences if item in type_01_set]
        covered_type_17 = [item for item in covered_competences if item in type_17_set]

        # Só é análise fiscal quando a janela cobre ao menos uma competência
        # Tipo 17. Tipo 01 isolado gera conferência documental, sem presumir imposto.
        request_kind = "ANALYSIS" if covered_type_17 else "VERIFICATION"
        if covered_type_17 and covered_type_01:
            purpose = "TYPE_17_ANALYSIS_AND_TYPE_01_VERIFICATION"
            description = (
                "PGDAS necessário para analisar as competências Tipo 17 e "
                "conferir as receitas declaradas nas competências da malha "
                "Tipo 01 cobertas pelo histórico do mesmo arquivo."
            )
        elif covered_type_17:
            purpose = "TYPE_17_ANALYSIS"
            description = (
                "PGDAS necessário para analisar a exposição fiscal Tipo 17 "
                "e confirmar a receita declarada na janela coberta."
            )
        else:
            purpose = "TYPE_01_DECLARATION_VERIFICATION"
            description = (
                "PGDAS solicitado para conferir a receita efetivamente "
                "declarada nas competências Tipo 01. A solicitação não "
                "gera, por si só, cálculo de imposto."
            )

        requests.append({
            "requested_competence": requested_competence,
            "request_kind": request_kind,
            "purpose": purpose,
            "covers_malha_competences": covered_competences,
            "covers_type_01_competences": covered_type_01,
            "covers_type_17_competences": covered_type_17,
            "covers_reflection_competences": [],
            "coverage_start": competence_from_index(coverage_start_index),
            "coverage_end": requested_competence,
            "status": "AWAITING_UPLOAD",
            "selection_rule": "LATEST_UNCOVERED_MALHA_COMPETENCE",
            "description": description,
        })

        for index in covered_indexes:
            del not_covered[index]

    return requests


def potential_reflection_requests(
    type_17_months: list[str],
    existing_requests: list[dict[str, Any]],
    latest_due_competence: str,
    history_months: int,
) -> list[dict[str, Any]]:
    """Planeja antecipadamente os PGDAS posteriores possíveis.

    Toda competência tipo 17 é tratada como uma correção potencial. Assim,
    o usuário recebe a lista completa antes de começar os uploads e não é
    surpreendido por um quarto documento depois da análise.
    """
    if not type_17_months:
        return []

    latest_due_index = month_index(latest_due_competence)
    reflection_targets: set[int] = set()

    for competence in type_17_months:
        correction_index = month_index(competence)
        end_index = min(correction_index + 12, latest_due_index)
        reflection_targets.update(
            range(correction_index + 1, end_index + 1)
        )

    covered_by_plan: set[int] = set()
    for request in existing_requests:
        requested_index = month_index(
            request["requested_competence"]
        )
        covered_by_plan.update(
            range(requested_index - history_months, requested_index + 1)
        )

    remaining = reflection_targets - covered_by_plan
    requests: list[dict[str, Any]] = []

    while remaining:
        requested_index = max(remaining)
        requested_competence = competence_from_index(requested_index)
        coverage_start_index = requested_index - history_months
        covered = sorted(
            index
            for index in remaining
            if coverage_start_index <= index <= requested_index
        )

        requests.append({
            "requested_competence": requested_competence,
            "request_kind": "REFLECTION",
            "purpose": "POTENTIAL_POSTERIOR_REVENUE_COVERAGE",
            "covers_malha_competences": [],
            "covers_type_01_competences": [],
            "covers_type_17_competences": [],
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
                "LATEST_UNCOVERED_POTENTIAL_REFLECTION_COMPETENCE"
            ),
            "description": (
                "PGDAS posterior solicitado antecipadamente para evitar "
                "novos pedidos depois da análise e cobrir os possíveis "
                "reflexos reais da RBT12."
            ),
        })

        for index in covered:
            remaining.discard(index)

    requests.sort(
        key=lambda item: month_index(item["requested_competence"])
    )
    return requests



def calculate_required_pgdas(
    malha_data: dict[str, Any],
    history_months: int = HISTORY_MONTHS,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Gera o plano completo de PGDAS para a malha.

    Regras:
    1. Solicitar PGDAS para conferir todas as competências da malha, inclusive Tipo 01.
    2. Apenas competências Tipo 17 alimentam a análise de exposição tributária.
    3. PGDAS posteriores são planejados antecipadamente para os reflexos potenciais
       das competências Tipo 17, sem projetar receitas futuras.
    4. O mesmo arquivo pode cobrir várias competências dentro do histórico disponível.
    """
    malha_data = normalize_malha_data(malha_data)
    work_months = malha_data.get("work_months", [])

    malha_competences = sorted(
        {
            month["competence"]
            for month in work_months
            if normalize_competence(month.get("competence"))
        },
        key=month_index,
    )
    type_01_months = sorted(
        {
            month["competence"]
            for month in work_months
            if "01" in month.get("types", [])
        },
        key=month_index,
    )
    type_17_months = sorted(
        {
            month["competence"]
            for month in work_months
            if "17" in month.get("types", [])
        },
        key=month_index,
    )

    latest_due = latest_normally_due_competence(as_of_date)
    requests = initial_document_requests(
        malha_competences,
        type_01_months,
        type_17_months,
        history_months,
    )
    reflection_requests = potential_reflection_requests(
        type_17_months,
        requests,
        latest_due,
        history_months,
    )

    for posterior in reflection_requests:
        existing = next(
            (
                request for request in requests
                if request["requested_competence"] == posterior["requested_competence"]
            ),
            None,
        )
        if existing is None:
            requests.append(posterior)
            continue

        if existing.get("request_kind") == "VERIFICATION":
            existing["request_kind"] = "VERIFICATION_AND_REFLECTION"
            existing["purpose"] = "TYPE_01_VERIFICATION_AND_POSTERIOR_COVERAGE"
            existing["description"] = (
                existing.get("description", "")
                + " O mesmo arquivo também cobre receitas posteriores "
                "para os possíveis reflexos da RBT12."
            )
        else:
            existing["request_kind"] = "ANALYSIS_AND_REFLECTION"
            existing["purpose"] = "TYPE_17_ANALYSIS_AND_POSTERIOR_COVERAGE"
            existing["description"] = (
                existing.get("description", "")
                + " O mesmo arquivo também cobre possíveis reflexos posteriores."
            )
        existing["covers_reflection_competences"] = sorted(
            set(existing.get("covers_reflection_competences", []))
            | set(posterior["covers_reflection_competences"]),
            key=month_index,
        )

    requests.sort(key=lambda item: month_index(item["requested_competence"]))

    full_reflection_end = None
    actual_reflection_end = None
    future_pending_competences: list[str] = []
    if type_17_months:
        latest_type_17_index = month_index(type_17_months[-1])
        full_end_index = latest_type_17_index + 12
        actual_end_index = min(full_end_index, month_index(latest_due))
        full_reflection_end = competence_from_index(full_end_index)
        actual_reflection_end = competence_from_index(actual_end_index)
        if full_end_index > actual_end_index:
            future_pending_competences = [
                competence_from_index(index)
                for index in range(actual_end_index + 1, full_end_index + 1)
            ]

    work_plan: list[dict[str, Any]] = []
    for month in work_months:
        types = month.get("types", [])
        actions: list[str] = []
        if "01" in types:
            actions.extend(["REVIEW_SPED_LFE", "VERIFY_PGDAS_DECLARATION"])
        if "17" in types:
            actions.extend([
                "IMPORT_PGDAS",
                "EVALUATE_TAX",
                "EVALUATE_RBT12_REFLECTIONS",
            ])
        work_plan.append({
            "competence": month["competence"],
            "types": types,
            "actions": actions,
            "requires_pgdas_analysis": "17" in types,
            "requires_pgdas_verification": "01" in types,
            "raw_row_count": month.get("raw_row_count", 0),
            "duplicate_count": month.get("duplicate_count", 0),
        })

    analysis_count = sum(
        request["request_kind"] in {"ANALYSIS", "ANALYSIS_AND_REFLECTION"}
        for request in requests
    )
    verification_count = sum(
        request["request_kind"] in {"VERIFICATION", "VERIFICATION_AND_REFLECTION"}
        for request in requests
    )
    reflection_count = sum(
        request["request_kind"] in {
            "REFLECTION", "ANALYSIS_AND_REFLECTION", "VERIFICATION_AND_REFLECTION"
        }
        for request in requests
    )

    covered_type_17 = {
        competence for request in requests
        for competence in request.get("covers_type_17_competences", [])
    }
    covered_type_01 = {
        competence for request in requests
        for competence in request.get("covers_type_01_competences", [])
    }
    covered_malha = {
        competence for request in requests
        for competence in request.get("covers_malha_competences", [])
    }
    uncovered_type_17 = [item for item in type_17_months if item not in covered_type_17]
    uncovered_type_01 = [item for item in type_01_months if item not in covered_type_01]
    uncovered_malha = [item for item in malha_competences if item not in covered_malha]

    rows_without_competence = [
        row.get("id", index + 1)
        for index, row in enumerate(malha_data.get("raw_rows", []) or [])
        if isinstance(row, dict)
        and not normalize_competence(row.get("competence") or row.get("reference"))
    ]
    summary_types = {
        normalize_type_code(code)
        for code in (malha_data.get("summary", {}).get("types_found") or [])
    }
    type_17_summary_without_competence = "17" in summary_types and not type_17_months
    type_01_summary_without_competence = "01" in summary_types and not type_01_months
    plan_valid = (
        not uncovered_type_17
        and not uncovered_type_01
        and not uncovered_malha
        and not rows_without_competence
        and not type_17_summary_without_competence
        and not type_01_summary_without_competence
        and (not malha_competences or bool(requests))
    )

    return {
        "planner": {
            "name": "checkfiscal-required-pgdas-planner",
            "strategy": "UPFRONT_COMPLETE_PLAN",
            "version": "2.4.0",
            "history_months": history_months,
            "planning_date": (as_of_date or date.today()).isoformat(),
        },
        "company": malha_data.get("contributor", {}),
        "summary": {
            "work_month_count": len(work_months),
            "type_01_month_count": len(type_01_months),
            "type_17_month_count": len(type_17_months),
            "type_01_only_month_count": sum(
                "01" in month.get("types", []) and "17" not in month.get("types", [])
                for month in work_months
            ),
            "analysis_pgdas_count": analysis_count,
            "verification_pgdas_count": verification_count,
            "reflection_pgdas_count": reflection_count,
            "required_pgdas_count": len(requests),
            "latest_normally_due_competence": latest_due,
            "actual_reflection_end": actual_reflection_end,
            "full_reflection_end": full_reflection_end,
            "future_pending_count": len(future_pending_competences),
        },
        "work_plan": work_plan,
        "validation": {
            "status": "VALID" if plan_valid else "ERROR",
            "malha_competences_detected": malha_competences,
            "type_01_competences_detected": type_01_months,
            "type_17_competences_detected": type_17_months,
            "uncovered_malha_competences": uncovered_malha,
            "uncovered_type_01_competences": uncovered_type_01,
            "uncovered_type_17_competences": uncovered_type_17,
            "rows_without_competence": rows_without_competence,
            "type_17_summary_without_competence": type_17_summary_without_competence,
            "type_01_summary_without_competence": type_01_summary_without_competence,
            "type_17_rows_without_competence": [
                row.get("id", index + 1)
                for index, row in enumerate(malha_data.get("raw_rows", []) or [])
                if isinstance(row, dict)
                and _row_type_code(row) == "17"
                and not normalize_competence(row.get("competence") or row.get("reference"))
            ],
            "message": (
                "Planejamento completo: todas as competências da malha têm cobertura PGDAS."
                if plan_valid else
                "Há linhas da malha sem competência identificada."
                if rows_without_competence else
                "Há competências Tipo 01 sem PGDAS de conferência planejado."
                if uncovered_type_01 or type_01_summary_without_competence else
                "Há competências Tipo 17 sem PGDAS planejado."
                if uncovered_type_17 or type_17_summary_without_competence else
                "Há competências da malha sem PGDAS planejado."
            ),
        },
        "required_pgdas": requests,
        "future_pending_competences": future_pending_competences,
        "post_upload_validation": {
            "required": True,
            "rule": "VALIDATE_ACTUAL_PGDAS_TIMELINE",
            "description": (
                "Após a leitura, confirmar se as competências que "
                "realmente tiveram correção possuem todas as receitas "
                "posteriores já vencidas. Competências antigas podem "
                "gerar pedidos complementares adicionais."
            ),
        },
    }

