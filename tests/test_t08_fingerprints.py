"""T08: fingerprints deterministicos e estados de atualizacao (sinteticos, sem rede/DB)."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from services import fingerprints as fp


def _malha(rows=None):
    rows = rows if rows is not None else [
        {"type": "17", "competence": "04/2025", "informed_cents": 100, "considered_cents": 200,
         "divergence_cents": 100, "id": 1, "page": 1, "table_row": 3, "confidence": 0.9,
         "source_cells": {"x": 1}, "duplicate": False, "duplicate_of": None},
        {"type": "01", "competence": "5/2025", "informed_cents": 50, "considered_cents": 60,
         "divergence_cents": 10, "id": 2, "page": 2},
    ]
    return {"malha": {"raw_rows": rows, "source_document": {"file_name": "a.pdf"}}, "company_cnpj": "1"}


def _pgdas(period="06/2025", revenue=1000, name="a.pdf", sha="h1", reader="v1"):
    return {
        "assessment": {"period": period, "revenue_summary": {"rpa": revenue}, "previous_revenues": {"05/2025": 5}},
        "source_document": {"file_name": name, "sha256": sha, "document_type": "PGDAS_DECLARATION"},
        "reader": {"version": reader},
        "coverage": {"history_start": "01/2024"},
        "derived_metrics": {"x": 1},
        "saved_at": "2026-01-01T00:00:00",
    }


def _conf(competence="04/2025", decision="CONFIRMED", increment=500):
    return {"competence": competence, "decision": decision, "created_at": "t",
            "analysis": {"competence": competence, "recommendation": {"pgdas_increment_cents": increment}}}


def _afp(process=None, pgdas=None, confs=None, concl=None):
    return fp.analysis_fingerprint(
        process or _malha(), pgdas if pgdas is not None else [_pgdas()],
        confs if confs is not None else [_conf()], concl or [])


def _tfp(a=None, **over):
    kw = dict(annex="I", scenario="CONSERVATIVE_FISCAL_EXPOSURE", standard_profile_confirmed=True,
              calculation_end="06/2026", full_reflection_end="11/2026", future_pending=["07/2026"])
    kw.update(over)
    return fp.tax_fingerprint(a or _afp(), **kw)


# --- canonical / digest
def test_canonical_is_ordered_and_types():
    assert fp.canonical({"b": 1, "a": [Decimal("1.50"), date(2026, 1, 2), (1, 2), {3, 1}]}) == \
        '{"a":["1.5","2026-01-02",[1,2],[1,3]],"b":1}'


def test_float_raises():
    with pytest.raises(TypeError):
        fp.canonical({"v": 1.5})


def test_decimal_precision_preserved():
    assert fp.digest("k", {"v": Decimal("0.0100")}) == fp.digest("k", {"v": Decimal("0.01")})
    assert fp.digest("k", {"v": Decimal("0.01")}) != fp.digest("k", {"v": Decimal("0.02")})


def test_digest_depends_on_kind():
    assert fp.digest("a", 1) != fp.digest("b", 1)


# --- analysis
def test_same_inputs_same_fingerprint():
    assert _afp() == _afp(process=deepcopy(_malha()), pgdas=[deepcopy(_pgdas())])
    assert len(_afp()) == 64


def test_order_of_documents_and_rows_irrelevant():
    rows = _malha()["malha"]["raw_rows"]
    a = [_pgdas("06/2025"), _pgdas("07/2025")]
    assert _afp(pgdas=a) == _afp(pgdas=a[::-1])
    assert _afp(process=_malha(rows)) == _afp(process=_malha(rows[::-1]))


def test_duplicate_document_and_rows_do_not_change():
    assert _afp(pgdas=[_pgdas(), _pgdas(name="copia.pdf", sha="h2")]) == _afp()
    rows = _malha()["malha"]["raw_rows"]
    assert _afp(process=_malha(rows + [dict(rows[0], id=99, duplicate=True)])) == _afp()


def test_irrelevant_changes_do_not_change():
    base = _afp()
    other = _pgdas(name="x.pdf", sha="zzz", reader="v9")
    other["saved_at"] = "2030"
    other["coverage"] = {"history_start": "01/2000"}
    assert _afp(pgdas=[other]) == base
    p = _malha()
    p["company_cnpj"] = "2"
    p["malha"]["raw_rows"][0].update(id=7, page=9, confidence=0.1, source_cells={})
    assert _afp(process=p) == base
    assert _afp(confs=[dict(_conf(), created_at="outro")]) == base


def test_relevant_changes_change():
    base = _afp()
    assert _afp(pgdas=[_pgdas(revenue=1001)]) != base
    assert _afp(pgdas=[_pgdas(period="07/2025")]) != base
    assert _afp(pgdas=[_pgdas(), _pgdas("07/2025")]) != base
    assert _afp(confs=[_conf(decision="REJECTED")]) != base
    assert _afp(confs=[_conf(increment=501)]) != base
    assert _afp(confs=[]) != base
    p = _malha()
    p["malha"]["raw_rows"][0]["informed_cents"] = 101
    assert _afp(process=p) != base
    assert _afp(concl=[{"competence": "04/2025", "status": "VALIDATED", "validated_pgdas_revenue_cents": 1,
                        "updated_at": "x"}]) != base


def test_competence_normalized():
    p = _malha()
    p["malha"]["raw_rows"][1]["competence"] = "05/2025"
    assert _afp(process=p) == _afp()
    assert _afp(confs=[_conf(competence="4/2025")]) == _afp()


# --- tax / charges
def test_tax_fingerprint_sensitivity():
    base = _tfp()
    assert _tfp() == base
    for over in (dict(annex="II"), dict(calculation_end="07/2026"), dict(full_reflection_end="12/2026"),
                 dict(future_pending=[]), dict(standard_profile_confirmed=False),
                 dict(scenario="VALIDATED_REGULARIZATION")):
        assert _tfp(**over) != base
    assert _tfp(future_pending=["08/2026", "07/2026"]) == _tfp(future_pending=["07/2026", "08/2026"])
    assert _tfp(_afp(pgdas=[_pgdas(revenue=1)])) != base


def test_only_selic_or_base_date_changes_charges():
    afp, tfp = _afp(), _tfp()
    kw = dict(update_date="2026-11-16", selic_used={"2026-01": "1.00"}, dues=[{"competence": "6/2025", "due_date": "2025-07-20"}])
    base = fp.charges_fingerprint(tfp, **kw)
    assert fp.charges_fingerprint(tfp, **kw) == base
    assert fp.charges_fingerprint(tfp, **dict(kw, selic_used={"2026-01": "1.01"})) != base
    assert fp.charges_fingerprint(tfp, **dict(kw, update_date="2026-11-17")) != base
    assert fp.charges_fingerprint(tfp, **dict(kw, dues=[{"competence": "06/2025", "due_date": "2025-07-21"}])) != base
    assert fp.charges_fingerprint(tfp, **dict(kw, dues=[{"competence": "06/2025", "due_date": "2025-07-20"}])) == base
    assert fp.charges_fingerprint(_tfp(annex="II"), **kw) != base
    assert _tfp(afp) == tfp and _afp() == afp  # tax e analysis nao dependem da Selic


def test_charges_inputs_from_result():
    result = {"source": {"update_date": "2026-11-16"},
              "rows": [{"competence": "6/2025", "due_date": "2025-07-20", "interest_rate": "0.1234"}]}
    assert fp.charges_inputs(result) == ("2026-11-16", {"06/2025": "0.1234"}, [{"competence": "06/2025", "due_date": "2025-07-20"}])


# --- estados
def _stored(tax_fp, annex="I"):
    return {"configuration": {"annex": annex}, "input_fingerprint": {"version": 1, "analysis": "a", "tax": tax_fp}}


def _charges(tax_fp, charges_fp="c"):
    return {"input_fingerprint": {"version": 1, "tax": tax_fp, "charges": charges_fp}, "source": {"update_date": "2026-11-16"}}


def test_states():
    f = fp.freshness_state
    assert f(None, None, "T", False)["tax"] == {"state": "NAO_CALCULADO", "reason": "NO_CALCULATION"}
    assert f(None, None, "T", True)["tax"] == {"state": "PENDENTE_DE_DADOS", "reason": "MISSING_DOCUMENTS"}
    assert f(_stored("T"), None, "T", False)["tax"] == {"state": "ATUALIZADO", "reason": "CURRENT"}
    assert f(_stored("T"), None, "X", False)["tax"] == {"state": "DESATUALIZADO", "reason": "INPUTS_CHANGED"}
    assert f({"configuration": {}}, None, "T", False)["tax"] == {"state": "DESATUALIZADO", "reason": "LEGACY_NO_FINGERPRINT"}
    assert f(_stored("T"), None, "T", False)["charges"]["state"] == "NAO_CALCULADO"
    ok = f(_stored("T"), _charges("T"), "T", False)
    assert ok["charges"] == {"state": "ATUALIZADO", "reason": "CURRENT"} and ok["can_emit"] is True
    assert f(_stored("T"), _charges("OLD"), "T", False)["charges"]["reason"] == "TAX_OUTDATED"
    stale = f(_stored("T"), _charges("T"), "X", False)
    assert stale["charges"] == {"state": "DESATUALIZADO", "reason": "TAX_OUTDATED"} and stale["can_emit"] is False
    assert f(_stored("T"), {"source": {}}, "T", False)["charges"]["reason"] == "LEGACY_NO_FINGERPRINT"
    assert f(None, None, "T", False)["can_emit"] is False


def test_period_advanced_vs_inputs_changed():
    f = fp.freshness_state
    stored = _stored("T")  # analysis gravada = "a"
    adv = f(stored, _charges("T"), "X", False, "a")
    assert adv["tax"] == {"state": "DESATUALIZADO", "reason": "PERIOD_ADVANCED"}
    assert adv["charges"] == {"state": "DESATUALIZADO", "reason": "TAX_OUTDATED"}
    assert adv["message"] == fp.PERIOD_ADVANCED_MESSAGE and adv["block_code"] == "CALCULATION_OUTDATED"
    chg = f(stored, _charges("T"), "X", False, "outra")
    assert chg["tax"]["reason"] == "INPUTS_CHANGED" and chg["message"] == fp.OUTDATED_MESSAGE
