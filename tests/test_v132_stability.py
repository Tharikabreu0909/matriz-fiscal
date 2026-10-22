from __future__ import annotations

from datetime import date
from pathlib import Path

import database
from readers.malha_reader import read_malha_pdf
from services.malha_merge import (
    malha_already_imported,
    merge_malhas,
)
from services.pgdas_planner import calculate_required_pgdas
from services.reflection_coverage import latest_normally_due_competence


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_same_malha_source_is_recognized_before_merge():
    malha = read_malha_pdf(
        Path("/mnt/data/malha fiscal aconchego(3).pdf")
    )
    assert malha_already_imported(malha, malha) is True


def test_visible_notices_remain_unique_while_raw_rows_are_preserved():
    malha = read_malha_pdf(
        Path("/mnt/data/malha fiscal aconchego(3).pdf")
    )
    merged = merge_malhas(malha, malha)
    july = next(
        item
        for item in merged["work_months"]
        if item["competence"] == "07/2025"
    )

    assert merged["summary"]["raw_row_count"] == 18
    assert july["raw_row_count"] == 4
    assert len(july["notices"]) == 2
    assert {item["type_code"] for item in july["notices"]} == {
        "01",
        "17",
    }


def test_planner_requests_old_and_recent_reflections_upfront():
    malha = read_malha_pdf(
        Path("/mnt/data/malha fiscal aconchego(3).pdf")
    )
    plan = calculate_required_pgdas(
        malha,
        as_of_date=date(2026, 7, 22),
    )
    requested = [
        item["requested_competence"]
        for item in plan["required_pgdas"]
    ]
    assert requested == [
        "06/2022",
        "06/2023",
        "11/2025",
        "06/2026",
    ]


def test_documents_use_one_central_upload_and_compact_status_rows():
    assert 'id="bulkPgdasDropzone"' in HTML
    assert 'id="documentProgressList"' not in HTML
    assert "Os cartões são indicadores de progresso" in HTML
    assert ".pgdas-upload input," in HTML
    assert ".pgdas-upload button," in HTML
    assert "setPgdasCardState(" in HTML
    assert "'loading'," in HTML
    assert "'Lendo'" in HTML
    assert "showWorkflowStep('documents',true)" in HTML


def test_new_malha_locks_old_documents_until_upload_finishes():
    assert "let awaitingNewMalhaUpload=false;" in HTML
    assert "awaitingNewMalhaUpload=true;" in HTML
    assert "&& !awaitingNewMalhaUpload" in HTML
    assert 'id="cancelNewMalhaUpload"' in HTML


def test_technical_memory_has_dark_theme_override():
    assert "#calculationStageContent .memory{" in HTML
    assert "#calculationStageContent .memory-item{" in HTML
    assert "color:#f5f8ff!important" in HTML


def test_company_delete_cascades_local_process_data(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "delete.db")
    database.init_db()
    company_id = database.create_company(
        cnpj="10689433000150",
        legal_name="Empresa para excluir",
    )
    process_id = database.create_process(
        malha={
            "contributor": {"legal_name": "Empresa para excluir"},
            "source_document": {"file_name": "malha.pdf"},
            "work_months": [],
        },
        pgdas_plan={"required_pgdas": []},
        company_cnpj="10689433000150",
        company_id=company_id,
    )
    database.append_process_event(
        process_id,
        "TEST",
        "Evento de teste",
    )

    database.delete_company(company_id)

    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS total FROM companies"
        ).fetchone()["total"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS total FROM processes"
        ).fetchone()["total"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS total FROM process_events"
        ).fetchone()["total"] == 0


def test_old_three_document_plan_is_refreshed_without_reupload(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "refresh.db")
    database.init_db()
    company_id = database.create_company(
        cnpj="09462429000175",
        legal_name="C E M CONFECCOES",
    )
    malha = read_malha_pdf(
        Path("/mnt/data/malha fiscal aconchego(3).pdf")
    )
    old_plan = calculate_required_pgdas(
        malha,
        as_of_date=date(2026, 7, 22),
    )
    old_plan["planner"]["version"] = "2.0.0"
    old_plan["required_pgdas"] = [
        item
        for item in old_plan["required_pgdas"]
        if item["requested_competence"] != "06/2023"
    ]
    old_plan["summary"]["required_pgdas_count"] = 3
    process_id = database.create_process(
        malha=malha,
        pgdas_plan=old_plan,
        company_cnpj="09462429000175",
        company_id=company_id,
    )

    import app

    process = app.ensure_current_pgdas_plan(
        database.get_process(process_id)
    )
    assert [
        item["requested_competence"]
        for item in process["pgdas_plan"]["required_pgdas"]
    ] == [
        "06/2022",
        "06/2023",
        "11/2025",
        latest_normally_due_competence(),
    ]
