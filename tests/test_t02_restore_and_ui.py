"""T02: 409 do restore ocupado e fluxo same-origin da UI (guard nao pode quebrar o app)."""
import logging

from fastapi.testclient import TestClient

SAME_ORIGIN = {"Origin": "http://127.0.0.1:8141", "Sec-Fetch-Site": "same-origin"}
COMPANY = {"cnpj": "10689433000150", "legal_name": "Empresa UI"}


def _client() -> TestClient:
    import app

    return TestClient(app.app, raise_server_exceptions=False)


def test_restore_busy_returns_409(monkeypatch):
    import app
    from database import DatabaseBusyError

    def busy(*args, **kwargs):
        raise DatabaseBusyError("ocupado")

    monkeypatch.setattr(app, "restore_backup", busy)
    response = _client().post(
        "/api/system/restore", files={"file": ("b.zip", b"x")}, headers=SAME_ORIGIN
    )
    assert response.status_code == 409
    assert "tente novamente" in response.json()["detail"]


def test_same_origin_ui_flow_passes_guard():
    client = _client()
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert client.get("/", headers=SAME_ORIGIN).status_code == 200
    assert client.get("/static/app.css", headers=SAME_ORIGIN).status_code == 200
    assert client.get("/api/health", headers=cross).status_code == 200  # F4
    created = client.post("/api/companies", json=COMPANY, headers=SAME_ORIGIN)
    assert created.status_code == 201
    company_id = created.json()["company"]["id"]
    assert client.get(f"/api/companies/{company_id}", headers=SAME_ORIGIN).status_code == 200
    assert client.get("/api/system/status", headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_blocked_log_neutralizes_newline_in_path(caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("checkfiscal"), "propagate", True)
    caplog.set_level("WARNING")
    response = _client().post("/api/x%0a2099-01-01 | INFO | falso", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    messages = [r.getMessage() for r in caplog.records if "CROSS_ORIGIN_BLOCKED" in r.getMessage()]
    assert messages and all("\n" not in m for m in messages)


def test_duplicate_host_header_via_client_is_400():
    response = _client().get("/api/health", headers=[("host", "testserver"), ("host", "testserver")])
    assert response.status_code == 400
