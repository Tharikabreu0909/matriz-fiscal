"""Fluxo T08 pela API: estados de atualização (ATUALIZADO/DESATUALIZADO/...).

Contrato: scratchpad t08-spec.md (§4 estados, §5 API, §8 testes).
Processo sintético: uma linha Tipo 17 na malha (competência 03/2026) e PGDAS
aceitos gravados direto com ``database.save_pgdas_document``. Sem PDF, sem rede
(Selic monkeypatched). Todos os testes são ``xfail(strict=True)`` até o agente
Selo implementar ``freshness``; ao implementar, remover as marcas.
"""
from __future__ import annotations

import json
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

import app
import database
from services import legal_charges
from tests.test_tax_engine import pgdas_with_timeline


CNPJ = "09.462.429/0001-75"
RECEITA_BASE = 1_000_000
RECEITA_NOVA = 1_400_000
DATA_BASE = "2026-11-16"
XFAIL = "T08: {}"


@pytest.fixture
def selic(monkeypatch):
    taxas: dict[str, Decimal] = {}
    monkeypatch.setattr(
        legal_charges,
        "fetch_bcb_monthly_selic",
        lambda inicio, fim, timeout_seconds=15: dict(taxas),
    )
    return taxas


@pytest.fixture
def client(selic):
    return TestClient(app.app)


def criar_processo() -> int:
    cid = database.create_company(CNPJ, "EMPRESA SINTETICA LTDA", default_annex="I")
    malha = {
        "contributor": {"legal_name": "EMPRESA SINTETICA LTDA", "cnpj": CNPJ},
        "raw_rows": [{
            "type_code": "17",
            "competence": "03/2026",
            "informed_cents": RECEITA_BASE,
            "considered_cents": RECEITA_BASE,
            "divergence_cents": 0,
        }],
        "work_months": [],
    }
    return database.create_process(malha, {"required_pgdas": []}, CNPJ, company_id=cid)


def salvar_pgdas(pid: int, periodo: str, receita: int = RECEITA_BASE) -> None:
    database.save_pgdas_document(
        pid,
        periodo,
        pgdas_with_timeline("01/2025", periodo, receita),
        "OK",
        "OK",
        True,
    )


def calcular_imposto(client: TestClient, pid: int):
    r = client.post("/api/calculate-tax", json={"process_id": pid, "annex": "I"})
    assert r.status_code == 200, r.text
    return r


def calcular_encargos(client: TestClient, pid: int, data: str = DATA_BASE):
    r = client.post(f"/api/calculate-legal-charges?process_id={pid}&update_date={data}")
    assert r.status_code == 200, r.text
    return r


def estado(client: TestClient, pid: int) -> dict:
    r = client.get(f"/api/process/{pid}")
    assert r.status_code == 200, r.text
    return r.json()["freshness"]


def contagens(pid: int) -> dict[str, int]:
    with database.connect() as connection:
        return {
            tabela: connection.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE process_id = ?", (pid,)
            ).fetchone()[0]
            for tabela in (
                "tax_calculations",
                "legal_charge_calculations",
                "client_reports",
            )
        }


def cenario_calculado_com_pgdas_novo(client: TestClient) -> int:
    """Imposto e encargos calculados; depois chega um PGDAS relevante novo."""
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    calcular_imposto(client, pid)
    calcular_encargos(client, pid)
    salvar_pgdas(pid, "02/2026", RECEITA_NOVA)
    return pid


@pytest.mark.xfail(strict=True, reason=XFAIL.format("sem PGDAS, imposto PENDENTE_DE_DADOS (MISSING_DOCUMENTS)"))
def test_processo_sem_pgdas_tem_imposto_pendente_de_dados(client):
    pid = criar_processo()
    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "PENDENTE_DE_DADOS"
    assert fresh["tax"]["reason"] == "MISSING_DOCUMENTS"
    assert fresh["report"]["can_emit"] is False


@pytest.mark.xfail(strict=True, reason=XFAIL.format("PGDAS aceito sem cálculo: imposto NAO_CALCULADO (NO_CALCULATION)"))
def test_processo_com_pgdas_sem_calculo_tem_imposto_nao_calculado(client):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "NAO_CALCULADO"
    assert fresh["tax"]["reason"] == "NO_CALCULATION"
    assert fresh["charges"]["state"] == "NAO_CALCULADO"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("calculate-tax ainda não devolve 'freshness' nem marca ATUALIZADO"))
def test_calculo_de_imposto_atualiza_estado_e_resposta_traz_freshness(client):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    r = calcular_imposto(client, pid)
    assert r.json()["freshness"]["tax"]["state"] == "ATUALIZADO"
    assert estado(client, pid)["tax"]["state"] == "ATUALIZADO"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("PGDAS relevante novo não torna imposto/encargos DESATUALIZADO"))
def test_novo_pgdas_relevante_torna_imposto_e_encargos_desatualizados(client):
    pid = cenario_calculado_com_pgdas_novo(client)
    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "DESATUALIZADO"
    assert fresh["tax"]["reason"] == "INPUTS_CHANGED"
    assert fresh["charges"]["state"] == "DESATUALIZADO"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("client-report ainda emite relatório com cálculo desatualizado (200)"))
def test_relatorio_com_calculo_desatualizado_retorna_409_e_nao_grava(client):
    pid = cenario_calculado_com_pgdas_novo(client)
    antes = contagens(pid)
    status_antes = database.get_process(pid)["status"]

    r = client.get(f"/api/client-report?process_id={pid}")

    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CALCULATION_OUTDATED"
    assert contagens(pid) == antes
    assert database.get_process(pid)["status"] == status_antes


@pytest.mark.xfail(strict=True, reason=XFAIL.format("recalcular só o imposto ainda não marca encargos com TAX_OUTDATED"))
def test_recalcular_so_imposto_deixa_encargos_desatualizados_por_tax_outdated(client):
    pid = cenario_calculado_com_pgdas_novo(client)
    calcular_imposto(client, pid)
    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "ATUALIZADO"
    assert fresh["charges"]["state"] == "DESATUALIZADO"
    assert fresh["charges"]["reason"] == "TAX_OUTDATED"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("encargos recalculados sobre imposto atual não viram ATUALIZADO/can_emit"))
def test_recalcular_encargos_torna_tudo_atualizado_e_relatorio_permitido(client):
    pid = cenario_calculado_com_pgdas_novo(client)
    calcular_imposto(client, pid)
    calcular_encargos(client, pid)
    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "ATUALIZADO"
    assert fresh["charges"]["state"] == "ATUALIZADO"
    assert fresh["report"]["can_emit"] is True
    assert client.get(f"/api/client-report?process_id={pid}").status_code == 200


@pytest.mark.xfail(strict=True, reason=XFAIL.format("mudança de Selic/data-base ainda não é isolada do imposto"))
def test_mudar_so_data_base_e_selic_nao_desatualiza_imposto(client, selic):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    calcular_imposto(client, pid)
    calcular_encargos(client, pid)

    selic.update({"2026-10": Decimal("0.0140")})
    calcular_encargos(client, pid, "2026-12-01")

    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "ATUALIZADO"
    assert fresh["charges"]["state"] == "ATUALIZADO"
    assert fresh["charges"]["base_date"] == "2026-12-01"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("cálculo sem input_fingerprint ainda não vira DESATUALIZADO (LEGACY_NO_FINGERPRINT)"))
def test_calculo_legado_sem_fingerprint_fica_desatualizado(client):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    calcular_imposto(client, pid)
    calcular_encargos(client, pid)

    # Simula cálculo legado apagando a chave no banco de TESTE.
    with database.connect() as connection:
        linha_id, texto = connection.execute(
            "SELECT id, calculation_json FROM tax_calculations "
            "WHERE process_id = ? ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
        dados = json.loads(texto)
        assert "input_fingerprint" in dados, "cálculo novo deve gravar input_fingerprint"
        dados.pop("input_fingerprint")
        connection.execute(
            "UPDATE tax_calculations SET calculation_json = ? WHERE id = ?",
            (json.dumps(dados), linha_id),
        )

    fresh = estado(client, pid)
    assert fresh["tax"]["state"] == "DESATUALIZADO"
    assert fresh["tax"]["reason"] == "LEGACY_NO_FINGERPRINT"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("encargos sobre imposto desatualizado ainda retornam 200"))
def test_encargos_com_imposto_desatualizado_retornam_409_tax_outdated(client):
    pid = cenario_calculado_com_pgdas_novo(client)
    r = client.post(f"/api/calculate-legal-charges?process_id={pid}&update_date={DATA_BASE}")
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "TAX_OUTDATED"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("GET /api/process ainda não traz 'freshness' (a invariante de não-escrita já vale hoje)"))
def test_get_processo_nao_grava_resultados_de_calculo(client):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    calcular_imposto(client, pid)
    calcular_encargos(client, pid)

    antes = contagens(pid)
    r = client.get(f"/api/process/{pid}")
    assert r.status_code == 200
    assert contagens(pid) == antes
    assert "freshness" in r.json()


@pytest.mark.xfail(strict=True, reason=XFAIL.format("recálculo ainda não devolve freshness ATUALIZADO (histórico já é preservado hoje)"))
def test_recalculo_preserva_calculos_antigos(client):
    pid = criar_processo()
    salvar_pgdas(pid, "03/2026")
    primeiro = calcular_imposto(client, pid).json()
    calcular_encargos(client, pid)
    salvar_pgdas(pid, "02/2026", RECEITA_NOVA)

    segundo = calcular_imposto(client, pid)

    with database.connect() as connection:
        ids = [
            linha[0]
            for linha in connection.execute(
                "SELECT id FROM tax_calculations WHERE process_id = ? ORDER BY id",
                (pid,),
            ).fetchall()
        ]
    assert ids == [primeiro["calculation_id"], segundo.json()["calculation_id"]]
    assert contagens(pid)["legal_charge_calculations"] == 1
    assert segundo.json()["freshness"]["tax"]["state"] == "ATUALIZADO"


@pytest.mark.xfail(strict=True, reason=XFAIL.format("relatório ainda mostra 'R$ 0,00' e texto antigo na competência pendente"))
def test_competencia_pendente_nao_aparece_como_zero_no_relatorio():
    from services.client_report import render_client_report

    modelo = {
        "company": {"name": "EMPRESA SINTETICA LTDA", "cnpj": CNPJ, "cfdf": ""},
        "generated_at": "16/11/2026 às 10:00",
        "scenario": "CONSERVATIVE_FISCAL_EXPOSURE",
        "update_date": "16/11/2026",
        "annex": "I",
        "summary": {
            "direct_tax_cents": 0,
            "reflection_tax_cents": 0,
            "principal_cents": 0,
            "fine_cents": 0,
            "interest_cents": 0,
            "updated_total_cents": 0,
            "impacted_month_count": 0,
            "calculation_end_competence": "02/2026",
            "full_reflection_end_competence": "02/2026",
            "future_pending_count": 0,
            "is_partial": True,
        },
        "competence_rows": [{
            "competence": "03/2026",
            "actions": ["Enviar PGDAS anterior"],
            "tax_increment_cents": 0,
            "updated_total_cents": 0,
        }],
        "missing_months": [{"competence": "03/2026", "missing_competences": ["03/2025"]}],
        "reflection_rows": [],
        "warnings": [],
    }

    html = render_client_report(modelo)
    linha = next(parte for parte in html.split("<tr>") if 'class="competence">03/2026' in parte)

    total_pendente = linha.rsplit('<td class="money">', 1)[1]
    assert not total_pendente.startswith("R$ 0,00")
    assert "Cálculo pendente de documentação" in linha
