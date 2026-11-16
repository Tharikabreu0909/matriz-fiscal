"""T08: estados de atualizacao no fluxo da API (sintetico, banco temporario, sem rede)."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app as app_module
import database
from services import legal_charges

RATE = [Decimal("1.00")]
TODAY = date(2026, 5, 15)
SCEN = "CONSERVATIVE_FISCAL_EXPOSURE"


def _month(i):
    y, m = divmod(i, 12)
    return f"{m + 1:02d}/{y}"


def _pgdas(period="04/2026", cents=1_000_000, name="a.pdf"):
    start = 2024 * 12
    end = int(period[3:]) * 12 + int(period[:2]) - 1
    return {
        "source_document": {"file_name": name, "sha256": name, "document_type": "PGDAS_DECLARATION"},
        "assessment": {
            "period": period,
            "revenue_summary": {"rpa": {"total_cents": cents}},
            "previous_revenues": [{"competence": _month(i), "total_cents": cents} for i in range(start, end)],
        },
    }


@pytest.fixture
def env(monkeypatch):
    database.init_db()
    real = app_module.calculate_reflection_coverage
    monkeypatch.setattr(app_module, "calculate_reflection_coverage",
                        lambda docs, confs, as_of=None, **kw: real(docs, confs, TODAY, **kw))
    monkeypatch.setattr(legal_charges, "fetch_bcb_monthly_selic", lambda s, e, **k: {
        f"{y:04d}-{m:02d}": RATE[0] for y, m in legal_charges.month_sequence(s.year, s.month, e.year, e.month)})
    RATE[0] = Decimal("1.00")
    malha = {"contributor": {"legal_name": "Teste"}, "source_document": {"file_name": "m.pdf"},
             "work_months": [{"competence": "04/2025", "notices": [
                 {"type_code": "17", "informed_cents": 1_000_000, "considered_cents": 1_500_000,
                  "divergence_cents": 500_000}]}]}
    pid = database.create_process(malha, {"required_pgdas": [{"requested_competence": "04/2025", "request_kind": "ANALYSIS"}]}, "000")
    client = TestClient(app_module.app)
    return client, pid


def _add_pgdas(pid, doc):
    database.save_pgdas_document(pid, doc["assessment"]["period"], doc, "OK", "OK", True)


def _confirm(client, pid):
    r = client.post(f"/api/confirm-analysis?process_id={pid}&competence=04/2025&decision=CONFIRMED")
    assert r.status_code == 200, r.text


def _calc_tax(client, pid):
    return client.post("/api/calculate-tax", json={"process_id": pid, "annex": "I"})


def _calc_charges(client, pid, date_="2026-05-15"):
    return client.post(f"/api/calculate-legal-charges?process_id={pid}&update_date={date_}")


def _fresh(client, pid):
    r = client.get(f"/api/process/{pid}")
    assert r.status_code == 200, r.text
    return r.json()["freshness"]


def _counts():
    with database.connect() as c:
        return [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("tax_calculations", "legal_charge_calculations", "client_reports")]


def _ready(client, pid):
    _add_pgdas(pid, _pgdas(period="04/2025", name="base.pdf"))
    _add_pgdas(pid, _pgdas())
    r = _calc_tax(client, pid)
    assert r.status_code == 200, r.text
    r = _calc_charges(client, pid)
    assert r.status_code == 200, r.text


def test_full_cycle(env):
    client, pid = env
    f = _fresh(client, pid)
    assert f["tax"]["state"] in {"NAO_CALCULADO", "PENDENTE_DE_DADOS"} and f["report"]["can_emit"] is False
    _add_pgdas(pid, _pgdas(period="04/2025", name="base.pdf"))
    _add_pgdas(pid, _pgdas())
    r = _calc_tax(client, pid)
    assert r.status_code == 200, r.text
    assert r.json()["freshness"]["tax"]["state"] == "ATUALIZADO"
    assert r.json()["tax_result"]["input_fingerprint"]["tax"]
    assert _fresh(client, pid)["charges"]["state"] == "NAO_CALCULADO"
    assert _calc_charges(client, pid).status_code == 200
    f = _fresh(client, pid)
    assert (f["tax"]["state"], f["charges"]["state"], f["report"]["can_emit"]) == ("ATUALIZADO", "ATUALIZADO", True)
    assert f["charges"]["base_date"] == "2026-05-15"
    assert client.get(f"/api/client-report?process_id={pid}").status_code == 200


def test_new_relevant_pgdas_outdates_and_blocks_report_then_recovers(env):
    client, pid = env
    _ready(client, pid)
    _add_pgdas(pid, _pgdas(period="03/2026", cents=2_000_000, name="b.pdf"))
    f = _fresh(client, pid)
    assert f["tax"]["state"] == "DESATUALIZADO" and f["charges"]["state"] == "DESATUALIZADO"
    before = _counts()
    r = client.get(f"/api/client-report?process_id={pid}")
    assert r.status_code == 409 and r.json()["code"] == "CALCULATION_OUTDATED"
    assert "Cálculo desatualizado" in r.json()["detail"]
    assert _counts() == before  # nao grava relatorio
    assert database.get_process(pid)["status"] != "CLIENT_REPORT_GENERATED"
    r = _calc_charges(client, pid)  # imposto velho: sem encargos novos
    assert r.status_code == 409 and r.json()["code"] == "TAX_OUTDATED"
    assert _counts() == before
    assert _calc_tax(client, pid).status_code == 200
    f = _fresh(client, pid)
    assert (f["tax"]["state"], f["charges"]["state"], f["charges"]["reason"]) == ("ATUALIZADO", "DESATUALIZADO", "TAX_OUTDATED")
    assert client.get(f"/api/client-report?process_id={pid}").status_code == 409
    assert _calc_charges(client, pid).status_code == 200
    f = _fresh(client, pid)
    assert (f["tax"]["state"], f["charges"]["state"]) == ("ATUALIZADO", "ATUALIZADO")
    assert client.get(f"/api/client-report?process_id={pid}").status_code == 200
    assert _counts()[:2] == [2, 2]  # historico preservado


def test_duplicate_pgdas_upload_does_not_outdate(env):
    client, pid = env
    _ready(client, pid)
    _add_pgdas(pid, _pgdas(name="copia.pdf"))
    assert _fresh(client, pid)["tax"]["state"] == "ATUALIZADO"


def test_process_status_is_read_only(env):
    client, pid = env
    _ready(client, pid)
    _add_pgdas(pid, _pgdas(period="03/2026", cents=2_000_000, name="b.pdf"))
    before = _counts()
    for _ in range(2):
        _fresh(client, pid)
    assert _counts() == before


def test_legacy_calculation_is_outdated(env):
    client, pid = env
    _ready(client, pid)
    legacy = database.latest_tax_calculation(pid, SCEN)
    del legacy["input_fingerprint"]
    database.save_tax_calculation(pid, "I", "STANDARD_FULL_REVENUE", legacy, SCEN)
    f = _fresh(client, pid)
    assert (f["tax"]["state"], f["tax"]["reason"]) == ("DESATUALIZADO", "LEGACY_NO_FINGERPRINT")
    assert client.get(f"/api/client-report?process_id={pid}").status_code == 409


def test_report_without_calculation_keeps_not_calculated_409(env):
    client, pid = env
    r = client.get(f"/api/client-report?process_id={pid}")
    assert r.status_code == 409 and r.json()["code"] == "NOT_CALCULATED"
    assert "Calcule primeiro o imposto" in r.json()["detail"]


def test_selic_change_outdates_only_charges_fingerprint(env):
    client, pid = env
    _ready(client, pid)
    first = database.latest_legal_charge_calculation(pid, SCEN)["input_fingerprint"]
    RATE[0] = Decimal("1.50")
    assert _calc_charges(client, pid).status_code == 200
    second = database.latest_legal_charge_calculation(pid, SCEN)["input_fingerprint"]
    assert first["tax"] == second["tax"] and first["charges"] != second["charges"]
