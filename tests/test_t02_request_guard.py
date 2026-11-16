"""Aceitação do guard de requisições (Fase 0, T02).

Regra: rejeição vira xfail(strict=True) até a T02; permissão fica verde hoje e
não pode regredir. Todo teste de rejeição prova ausência de efeito: o estado
do banco temporário (linhas de todas as tabelas) e os arquivos de backup,
suporte e documentos ficam idênticos antes e depois. Os handlers são trocados
por um sentinela que falha, então a rejeição também prova que o handler não
foi alcançado (corpo do upload não lido nem gravado).

Host padrão do TestClient é "testserver", permitido só na suíte (conftest).
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import runtime_paths

XFAIL = pytest.mark.xfail(
    strict=True, reason="T02: guard de requisicoes ainda nao implementado"
)
EVIL = "https://evil.example"
LOCAL = "http://127.0.0.1:8141"
COMPANY = {
    "cnpj": "10689433000150",
    "legal_name": "Empresa T02",
    "trade_name": "",
    "state_registration": "",
    "city": "",
    "state": "",
    "default_annex": "I",
    "notes": "",
}
HANDLERS_TO_BLOCK = (
    "create_company", "update_company", "delete_company", "create_process",
    "update_process_malha", "invalidate_process_analysis", "save_pgdas_document",
    "register_stored_document", "save_analysis_confirmation", "save_tax_calculation",
    "save_legal_charge_calculation", "save_client_report", "create_backup",
    "restore_backup", "create_support_bundle",
)


def pdf_bytes() -> bytes:
    """PDF sintético mínimo, gerado em memória (nunca PDF real)."""
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def invalid_zip() -> bytes:
    return b"PK\x05\x06" + bytes(18)


def _snapshot() -> dict:
    """Estado observável: conteúdo de todas as tabelas e lista de arquivos."""
    connection = sqlite3.connect(runtime_paths.DB_PATH)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        rows = {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            for table in tables
        }
    finally:
        connection.close()
    files = {
        directory.name: sorted(
            str(path.relative_to(directory))
            for path in directory.rglob("*")
            if path.is_file()
        )
        for directory in (
            runtime_paths.BACKUPS_DIR,
            runtime_paths.SUPPORT_DIR,
            runtime_paths.DOCUMENTS_DIR,
        )
    }
    return {
        "counts": {table: len(value) for table, value in rows.items()},
        "digest": hashlib.sha256(repr(rows).encode()).hexdigest(),
        "files": files,
    }


@pytest.fixture
def client() -> TestClient:
    import app

    return TestClient(app.app, raise_server_exceptions=False)


@pytest.fixture
def seeded(client: TestClient) -> dict:
    """Empresa e processo reais no banco temporário (criação sem cabeçalhos)."""
    import database

    created = client.post("/api/companies", json=COMPANY)
    assert created.status_code == 201
    company_id = created.json()["company"]["id"]
    process_id = database.create_process(
        malha={}, pgdas_plan={}, company_cnpj=COMPANY["cnpj"], company_id=company_id
    )
    return {"company_id": company_id, "process_id": process_id}


@pytest.fixture
def handler_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falha se um handler de escrita ou de arquivo for alcançado."""
    import app

    def boom(*args, **kwargs):
        raise AssertionError("handler alcancado: a requisicao deveria ter sido bloqueada antes")

    for name in HANDLERS_TO_BLOCK:
        monkeypatch.setattr(app, name, boom)


# ---------------------------------------------------------------- Host

HOSTS_BLOCKED = ["evil.com", "127.0.0.1.evil.com", "127.0.0.1:9999", "localhost:3000"]
HOSTS_ALLOWED = [
    "127.0.0.1:8141", "localhost:8141", "127.0.0.1:8145",
    "localhost:8145", "127.0.0.1:8146", "localhost:8146", "testserver",
]


@pytest.mark.parametrize("host", HOSTS_BLOCKED)
@pytest.mark.parametrize("path", ["/", "/api/health"])
def test_host_fora_da_lista_retorna_400(client, host, path):
    response = client.get(path, headers={"Host": host})
    assert response.status_code == 400
    assert response.json().get("code") == "HOST_NOT_ALLOWED"


def test_dns_rebinding_no_restore_nao_substitui_banco(client, seeded, handler_guard):
    before = _snapshot()
    response = client.post(
        "/api/system/restore",
        files={"file": ("backup.zip", invalid_zip(), "application/zip")},
        headers={"Host": "rebind.attacker.example"},
    )
    assert response.status_code == 400
    assert response.json().get("code") == "HOST_NOT_ALLOWED"
    assert _snapshot() == before


@pytest.mark.parametrize("host", HOSTS_ALLOWED)
def test_host_permitido_chega_ao_handler(client, host):
    response = client.get("/api/health", headers={"Host": host})
    assert response.status_code == 200


# ---------------------------------------------------------------- Origin

ORIGINS_BLOCKED = [
    EVIL,
    "null",
    "http://127.0.0.1.evil.example:8141",
    "https://127.0.0.1:8141",  # esquema diferente
    "http://127.0.0.1:9999",  # porta diferente
    "http://localhost:3000",  # same-site, outra porta
]
ORIGINS_ALLOWED = ["http://127.0.0.1:8141", "http://localhost:8145", "http://127.0.0.1:8146"]


@pytest.mark.parametrize("origin", ORIGINS_BLOCKED)
def test_origin_nao_autorizado_bloqueia_escrita(client, seeded, handler_guard, origin):
    before = _snapshot()
    response = client.post("/api/companies", json=COMPANY, headers={"Origin": origin})
    assert response.status_code == 403
    assert response.json().get("code") == "CROSS_ORIGIN_BLOCKED"
    assert _snapshot() == before


@pytest.mark.parametrize("origin", ORIGINS_ALLOWED)
def test_origin_autorizado_passa(client, origin):
    response = client.post("/api/companies", json=COMPANY, headers={"Origin": origin})
    assert response.status_code == 201


# ---------------------------------------------------------------- Sec-Fetch-Site e cabeçalhos combinados

CONTRADICTORY_HEADERS = [
    pytest.param({"Sec-Fetch-Site": "cross-site"}, id="cross-site"),
    pytest.param({"Sec-Fetch-Site": "same-site"}, id="same-site"),
    pytest.param({"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-site"}, id="same-site-outra-porta"),
    pytest.param({"Origin": LOCAL, "Sec-Fetch-Site": "cross-site"}, id="origin-ok-sfs-cross"),
    pytest.param({"Origin": EVIL, "Sec-Fetch-Site": "same-origin"}, id="origin-evil-sfs-same-origin"),
]


@pytest.mark.parametrize("headers", CONTRADICTORY_HEADERS)
def test_sec_fetch_e_origin_bloqueiam_escrita(client, seeded, handler_guard, headers):
    before = _snapshot()
    response = client.post("/api/companies", json=COMPANY, headers=headers)
    assert response.status_code == 403
    assert response.json().get("code") == "CROSS_ORIGIN_BLOCKED"
    assert _snapshot() == before


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"Sec-Fetch-Site": "same-origin"}, id="same-origin"),
        pytest.param({"Origin": LOCAL, "Sec-Fetch-Site": "same-origin"}, id="origin-ok-same-origin"),
        pytest.param({}, id="sem-cabecalhos-cli"),
    ],
)
def test_mesma_origem_ou_cliente_local_passa(client, headers):
    response = client.post("/api/companies", json=COMPANY, headers=headers)
    assert response.status_code == 201


# ---------------------------------------------------------------- Escritas: todas as rotas que alteram estado

def _pdf_file():
    return {"file": ("documento.pdf", pdf_bytes(), "application/pdf")}


STATE_CHANGING = [
    pytest.param(lambda c, h, s: c.post("/api/companies", json=COMPANY, headers=h), id="POST-companies"),
    pytest.param(lambda c, h, s: c.patch(f"/api/companies/{s['company_id']}", json={"legal_name": "X"}, headers=h), id="PATCH-companies"),
    pytest.param(lambda c, h, s: c.delete(f"/api/companies/{s['company_id']}", headers=h), id="DELETE-companies"),
    pytest.param(lambda c, h, s: c.post("/api/analyze-malha", files=_pdf_file(), headers=h), id="POST-analyze-malha"),
    pytest.param(lambda c, h, s: c.post(f"/api/upload-pgdas?process_id={s['process_id']}&competence=2025-01", files=_pdf_file(), headers=h), id="POST-upload-pgdas"),
    pytest.param(lambda c, h, s: c.post(f"/api/upload-pgdas-auto?process_id={s['process_id']}", files=[("files", ("p.pdf", pdf_bytes(), "application/pdf"))], headers=h), id="POST-upload-pgdas-auto"),
    pytest.param(lambda c, h, s: c.post("/api/system/restore", files={"file": ("backup.zip", invalid_zip(), "application/zip")}, headers=h), id="POST-system-restore"),
    pytest.param(lambda c, h, s: c.post(f"/api/confirm-analysis?process_id={s['process_id']}&competence=2025-01", headers=h), id="POST-confirm-analysis"),
    pytest.param(lambda c, h, s: c.post("/api/calculate-tax", json={"process_id": s["process_id"], "annex": "I"}, headers=h), id="POST-calculate-tax"),
    pytest.param(lambda c, h, s: c.post(f"/api/calculate-legal-charges?process_id={s['process_id']}&update_date=2026-01-31", headers=h), id="POST-calculate-legal-charges"),
    pytest.param(lambda c, h, s: c.put("/api/health", headers=h), id="PUT-sem-rota-deve-dar-403-nao-405"),
]


@pytest.mark.parametrize("send", STATE_CHANGING)
def test_origin_externo_bloqueia_todas_as_escritas(client, seeded, handler_guard, send):
    before = _snapshot()
    response = send(client, {"Origin": EVIL}, seeded)
    assert response.status_code == 403
    assert response.json().get("code") == "CROSS_ORIGIN_BLOCKED"
    assert _snapshot() == before


@pytest.mark.parametrize("send", STATE_CHANGING[:1] + STATE_CHANGING[6:7] + STATE_CHANGING[8:9])
def test_cross_site_bloqueia_escritas_selecionadas(client, seeded, handler_guard, send):
    before = _snapshot()
    response = send(client, {"Sec-Fetch-Site": "cross-site"}, seeded)
    assert response.status_code == 403
    assert _snapshot() == before


def test_json_sem_content_type_nao_contorna_o_guard(client, seeded, handler_guard):
    before = _snapshot()
    response = client.post(
        "/api/companies",
        content=b'{"cnpj": "10689433000150", "legal_name": "Via Blob"}',
        headers={"Origin": EVIL},
    )
    assert response.status_code == 403
    assert _snapshot() == before


def test_json_sem_content_type_em_calculo_cross_site(client, seeded, handler_guard):
    before = _snapshot()
    response = client.post(
        "/api/calculate-tax",
        content=f'{{"process_id": {seeded["process_id"]}, "annex": "I"}}'.encode(),
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert _snapshot() == before


def test_barra_final_cross_origin_da_403_e_nao_307(client, seeded, handler_guard):
    before = _snapshot()
    response = client.post(
        "/api/system/restore/",
        files={"file": ("backup.zip", invalid_zip(), "application/zip")},
        headers={"Origin": EVIL},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert _snapshot() == before


# ---------------------------------------------------------------- GET com efeito colateral (ou leitura de dados)

GET_GUARDED = [
    pytest.param(lambda s: "/api/system/backup", id="backup"),
    pytest.param(lambda s: "/api/system/support-bundle", id="support-bundle"),
    pytest.param(lambda s: f"/api/client-report?process_id={s['process_id']}", id="client-report"),
    pytest.param(lambda s: f"/api/process/{s['process_id']}", id="process"),
    pytest.param(lambda s: f"/api/companies/{s['company_id']}", id="companies-id"),
    pytest.param(lambda s: "/api/companies", id="companies-list"),
    pytest.param(lambda s: "/api/events", id="events"),
    pytest.param(lambda s: "/api/system/status", id="system-status"),
    pytest.param(lambda s: f"/api/tax-setup?process_id={s['process_id']}", id="tax-setup"),
    pytest.param(lambda s: f"/api/process/{s['process_id']}/documents", id="process-documents"),
    pytest.param(lambda s: "/api/documents/1/download", id="document-download"),
]


@pytest.mark.parametrize("path", GET_GUARDED)
def test_get_sob_api_cross_site_bloqueado(client, seeded, handler_guard, path):
    before = _snapshot()
    response = client.get(path(seeded), headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert response.json().get("code") == "CROSS_ORIGIN_BLOCKED"
    assert _snapshot() == before


def test_client_report_same_site_bloqueado_sem_relatorio(client, seeded, handler_guard):
    before = _snapshot()
    response = client.get(
        f"/api/client-report?process_id={seeded['process_id']}",
        headers={"Sec-Fetch-Site": "same-site"},
    )
    assert response.status_code == 403
    assert _snapshot() == before


def test_head_em_backup_nao_cria_arquivo(client, seeded, handler_guard):
    before = _snapshot()
    response = client.head("/api/system/backup")
    assert response.status_code == 405
    assert _snapshot() == before


def test_bloqueio_registrado_em_log_sem_query_nem_corpo(client, seeded, handler_guard, caplog, monkeypatch):
    caplog.set_level("INFO")
    # o logger do app nao propaga ao root (app_logging.propagate=False): liga o caplog nele
    monkeypatch.setattr(logging.getLogger("checkfiscal"), "propagate", True)
    client.post(
        f"/api/confirm-analysis?process_id={seeded['process_id']}&competence=2026-01",
        headers={"Origin": EVIL},
    )
    blocked = [
        record for record in caplog.records
        if record.levelno >= 30
        and "/api/confirm-analysis" in record.getMessage()
        and "POST" in record.getMessage()
    ]
    assert blocked, "esperado log WARNING com metodo e rota do bloqueio"
    assert all("2026-01" not in record.getMessage() for record in blocked)


# ---------------------------------------------------------------- Permissão (verde hoje; não pode regredir)

@pytest.mark.parametrize(
    "path,headers",
    [
        pytest.param("/", {"Sec-Fetch-Site": "cross-site"}, id="index"),
        pytest.param("/static/app.css", {"Sec-Fetch-Site": "cross-site"}, id="app-css"),
        pytest.param("/api/health", {"Sec-Fetch-Site": "cross-site"}, id="health"),
    ],
)
def test_leitura_publica_cross_site_permitida(client, path, headers):
    assert client.get(path, headers=headers).status_code == 200


def test_get_com_sec_fetch_none_passa(client, seeded):
    response = client.get(f"/api/companies/{seeded['company_id']}", headers={"Sec-Fetch-Site": "none"})
    assert response.status_code == 200


def test_restore_mesma_origem_zip_invalido_422_sem_efeito(client, seeded):
    before = _snapshot()
    response = client.post(
        "/api/system/restore",
        files={"file": ("backup.zip", invalid_zip(), "application/zip")},
        headers={"Origin": LOCAL, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 422
    assert _snapshot() == before


def test_analyze_malha_mesma_origem_chega_ao_handler(client):
    response = client.post(
        "/api/analyze-malha",
        files=_pdf_file(),
        headers={"Origin": LOCAL, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code != 403
    assert "CROSS_ORIGIN_BLOCKED" not in response.text


def test_options_nao_ganha_cabecalhos_cors(client):
    response = client.options(
        "/api/companies",
        headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"},
    )
    assert not [name for name in response.headers if name.lower().startswith("access-control-")]


def test_interface_usa_apenas_caminhos_relativos_para_api():
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    assert re.search(r"""['"`]https?://[^'"`\s)]*/api/""", html) is None
