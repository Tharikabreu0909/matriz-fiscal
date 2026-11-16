"""Fingerprints deterministicos e estados de atualizacao (T08). Funcoes puras: sem I/O, rede ou DB."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from services.pgdas_planner import normalize_competence, normalize_type_code

RULES = {"analysis": 1, "tax": 1, "charges": 1}  # subir quando a regra correspondente mudar

OUTDATED_MESSAGE = (
    "Cálculo desatualizado. Os documentos ou parâmetros deste processo foram alterados após o último "
    "cálculo. Recalcule o imposto e os encargos antes de emitir um novo relatório."
)
PERIOD_ADVANCED_MESSAGE = (
    "Um novo mÃªs venceu desde o Ãºltimo cÃ¡lculo. Envie os PGDAS pendentes do plano, se houver, e recalcule "
    "o imposto e os encargos antes de emitir um novo relatÃ³rio."
)
MSG_TAX_MISSING = "Calcule primeiro o imposto e os reflexos do cenário selecionado."
MSG_CHARGES_MISSING = "Calcule primeiro a multa e os juros do cenário selecionado."


def _norm(obj: Any) -> Any:
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        raise TypeError("float proibido no fingerprint: use centavos inteiros ou Decimal")
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f")
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _norm(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_norm(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((_norm(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    raise TypeError(f"tipo nao suportado no fingerprint: {type(obj).__name__}")


def canonical(obj: Any) -> str:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(kind: str, payload: Any) -> str:
    return hashlib.sha256(canonical({"kind": kind, "payload": payload}).encode("ascii")).hexdigest()


def _sorted_unique(items: list[Any]) -> list[Any]:
    return sorted({canonical(i) for i in items})


def _malha_rows(process: dict) -> list[str]:
    rows = []
    for row in (process.get("malha") or {}).get("raw_rows") or []:
        code = normalize_type_code(row.get("type_code") or row.get("type") or row.get("type_description"))
        # id/page/table_row/confidence/source_cells/duplicate: posicao no PDF, nao conteudo fiscal
        rows.append([code, normalize_competence(row.get("competence") or row.get("reference")),
                     row.get("informed_cents"), row.get("considered_cents"), row.get("divergence_cents")])
    return _sorted_unique(rows)


def _pgdas_docs(accepted: list[dict]) -> list[str]:
    # source_document/reader/coverage/derived_metrics/saved_at excluidos: hash, nome, versao e derivados nao mudam o fiscal
    return _sorted_unique([
        [(d.get("source_document") or {}).get("document_type", ""), d.get("assessment") or {}] for d in accepted
    ])


def _confirmations(confirmations: list[dict]) -> list[str]:
    out = []
    for c in confirmations:
        rec = (c.get("analysis") or {}).get("recommendation") or {}
        # so os valores em centavos que alimentam o calculo; timestamps ficam fora
        cents = {k: v for k, v in rec.items() if k.endswith("_cents") and isinstance(v, int)}
        out.append([normalize_competence(c.get("competence")), c.get("decision"), cents])
    return _sorted_unique(out)


def _conclusions(conclusions: list[dict]) -> list[str]:
    # created_at/updated_at/notes excluidos: nao entram na conta
    return _sorted_unique([
        [normalize_competence(c.get("competence")), c.get("status"), c.get("validated_pgdas_revenue_cents"),
         c.get("validated_sped_lfe_revenue_cents"), c.get("reason_code")] for c in conclusions
    ])


def analysis_fingerprint(process: dict, accepted_pgdas: list[dict], confirmations: list[dict],
                         accounting_conclusions: list[dict]) -> str:
    # CNPJ/razao social/nome de arquivo fora: nao mudam o calculo
    return digest("analysis", {
        "malha": _malha_rows(process), "pgdas": _pgdas_docs(accepted_pgdas),
        "confirmations": _confirmations(confirmations), "conclusions": _conclusions(accounting_conclusions),
        "rules": RULES["analysis"],
    })


def tax_fingerprint(analysis_fp: str, *, annex: str, scenario: str, standard_profile_confirmed: bool,
                    calculation_end: str, full_reflection_end: str, future_pending: list[str]) -> str:
    return digest("tax", {
        "analysis": analysis_fp, "annex": annex, "scenario": scenario,
        "standard_profile_confirmed": standard_profile_confirmed,
        "calculation_end": normalize_competence(calculation_end),
        "full_reflection_end": normalize_competence(full_reflection_end),
        "future_pending": sorted(normalize_competence(c) for c in future_pending),
        "rules": RULES["tax"],
    })


# registro de auditoria: nÃ£o Ã© comparado na leitura; sÃ³ o tax fp decide o estado dos encargos
def charges_fingerprint(tax_fp: str, *, update_date: str, selic_used: dict[str, str], dues: list[dict]) -> str:
    return digest("charges", {
        "tax": tax_fp, "update_date": update_date, "selic_used": selic_used,
        "dues": sorted([normalize_competence(d["competence"]), d["due_date"]] for d in dues),
        "rules": RULES["charges"],
    })


def charges_inputs(result: dict) -> tuple[str, dict[str, str], list[dict]]:
    """(data-base, Selic efetiva por competencia, vencimentos) lidos do resultado de encargos."""
    rows = result.get("rows") or []
    # a taxa de juros aplicada por linha e a Selic efetivamente usada (legal_charges nao expoe a serie)
    selic = {normalize_competence(r["competence"]): str(r["interest_rate"]) for r in rows}
    dues = [{"competence": normalize_competence(r["competence"]), "due_date": r["due_date"]} for r in rows]
    return (result.get("source") or {}).get("update_date", ""), selic, dues


def freshness_state(tax_result: dict | None, charges_result: dict | None, current_tax_fp: str | None,
                    blocked_by_documents: bool, current_analysis_fp: str | None = None) -> dict:
    """Estado de tax/charges e can_emit. current_tax_fp: fingerprint recalculado agora (None se nao calculavel)."""
    if tax_result is None:
        tax = ("PENDENTE_DE_DADOS", "MISSING_DOCUMENTS") if blocked_by_documents else ("NAO_CALCULADO", "NO_CALCULATION")
    else:
        stored = (tax_result.get("input_fingerprint") or {}).get("tax")
        if not stored:
            tax = ("DESATUALIZADO", "LEGACY_NO_FINGERPRINT")
        elif stored == current_tax_fp:
            tax = ("ATUALIZADO", "CURRENT")
        elif (tax_result["input_fingerprint"].get("analysis") == current_analysis_fp):
            # documentos/decisoes iguais: so o calendario avancou (mes venceu)
            tax = ("DESATUALIZADO", "PERIOD_ADVANCED")
        else:
            tax = ("DESATUALIZADO", "INPUTS_CHANGED")

    if charges_result is None:
        charges = ("NAO_CALCULADO", "NO_CALCULATION")
    else:
        used = (charges_result.get("input_fingerprint") or {}).get("tax")
        stored_tax = (tax_result or {}).get("input_fingerprint", {}).get("tax")
        if not used:
            charges = ("DESATUALIZADO", "LEGACY_NO_FINGERPRINT")
        elif tax[0] == "ATUALIZADO" and used == stored_tax:
            charges = ("ATUALIZADO", "CURRENT")
        else:
            charges = ("DESATUALIZADO", "TAX_OUTDATED")

    can_emit = tax[0] == "ATUALIZADO" and charges[0] == "ATUALIZADO"
    if tax_result is None:
        code, message = "NOT_CALCULATED", MSG_TAX_MISSING
    elif charges_result is None:
        code, message = "NOT_CALCULATED", MSG_CHARGES_MISSING
    elif not can_emit:
        code = "CALCULATION_OUTDATED"
        message = PERIOD_ADVANCED_MESSAGE if tax[1] == "PERIOD_ADVANCED" else OUTDATED_MESSAGE
    else:
        code, message = None, None
    return {
        "tax": {"state": tax[0], "reason": tax[1]},
        "charges": {"state": charges[0], "reason": charges[1]},
        "can_emit": can_emit,
        "block_code": code,
        "message": message,
    }
