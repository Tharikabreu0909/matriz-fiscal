import database


def test_company_registration_and_overview(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "companies.db")
    database.init_db()
    company_id = database.create_company(
        cnpj="10.689.433/0001-50",
        legal_name="Empresa Teste Ltda",
        city="Brasília",
        state="DF",
        default_annex="I",
    )
    company = database.get_company(company_id)
    assert company["cnpj"] == "10689433000150"
    assert company["default_annex"] == "I"
    overview = database.list_companies()
    assert overview[0]["process_status"] == "HEALTHY"
    assert overview[0]["active_process_id"] is None


def test_company_cnpj_is_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "unique.db")
    database.init_db()
    database.create_company("10689433000150", "Empresa A")
    try:
        database.create_company("10.689.433/0001-50", "Empresa B")
    except ValueError as error:
        assert "Já existe" in str(error)
    else:
        raise AssertionError("CNPJ duplicado deveria ser bloqueado")


def test_recent_events_and_company_operational_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "events.db")
    database.init_db()
    company_id = database.create_company("10689433000150", "Empresa Métrica")
    malha = {
        "contributor": {"legal_name": "Empresa Métrica", "cfdf": "123"},
        "source_document": {"file_name": "malha.pdf"},
        "work_months": [
            {"competence": "01/2025", "types": ["17"]},
            {"competence": "02/2025", "types": ["01", "17"]},
        ],
    }
    plan = {"required_pgdas": [{"requested_competence": "02/2025"}]}
    process_id = database.create_process(malha, plan, "10689433000150", company_id=company_id)
    database.append_process_event(process_id, "MALHA_INCLUDED", "Malha incluída")
    company = database.list_companies()[0]
    assert company["competence_count"] == 2
    assert company["type_01_count"] == 1
    assert company["type_17_count"] == 2
    assert company["required_pgdas_count"] == 1
    events = database.list_recent_process_events()
    assert events[0]["company_name"] == "Empresa Métrica"
    assert events[0]["title"] == "Malha incluída"
