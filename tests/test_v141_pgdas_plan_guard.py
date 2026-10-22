from copy import deepcopy
import json
from datetime import date
from pathlib import Path

from services.pgdas_planner import calculate_required_pgdas, normalize_malha_data


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
BATCH = (ROOT / "INICIAR_CHECKFISCAL_WINDOWS.bat").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop_launcher.py").read_text(encoding="utf-8")
LINUX = (ROOT / "iniciar_linux_mac.sh").read_text(encoding="utf-8")


def aconchego_malha():
    payload = json.loads(
        (ROOT / "tests" / "fixtures" / "aconchego.json").read_text(
            encoding="utf-8"
        )
    )
    return deepcopy(payload["malha"])


def test_stale_work_month_types_are_recovered_from_raw_rows():
    malha = aconchego_malha()
    july = next(
        month for month in malha["work_months"]
        if month["competence"] == "07/2025"
    )
    july["types"] = ["01"]

    normalized = normalize_malha_data(malha)
    normalized_july = next(
        month for month in normalized["work_months"]
        if month["competence"] == "07/2025"
    )
    assert normalized_july["types"] == ["01", "17"]

    plan = calculate_required_pgdas(normalized, as_of_date=date(2026, 8, 7))
    assert "07/2025" in plan["validation"]["type_17_competences_detected"]
    assert plan["validation"]["status"] == "VALID"
    assert plan["required_pgdas"]


def test_numeric_type_17_still_generates_pgdas_requests():
    malha = {
        "contributor": {},
        "summary": {"types_found": [17]},
        "raw_rows": [],
        "work_months": [{"competence": "11/2025", "types": [17]}],
    }
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 8, 7))
    assert plan["summary"]["type_17_month_count"] == 1
    assert plan["summary"]["required_pgdas_count"] > 0
    assert plan["validation"]["status"] == "VALID"


def test_type_17_without_a_competence_is_a_planning_error():
    malha = {
        "contributor": {},
        "summary": {"types_found": ["17"]},
        "raw_rows": [{"id": 9, "type_code": "17", "reference": "referência ilegível"}],
        "work_months": [],
    }
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 8, 7))
    assert plan["validation"]["status"] == "ERROR"
    assert plan["validation"]["type_17_rows_without_competence"] == [9]


def test_type_01_only_malha_requires_pgdas_for_declaration_verification():
    malha = {
        "contributor": {},
        "summary": {"types_found": ["01"]},
        "raw_rows": [],
        "work_months": [{"competence": "06/2025", "types": ["01"]}],
    }
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 8, 7))
    assert plan["summary"]["type_17_month_count"] == 0
    assert plan["summary"]["type_01_month_count"] == 1
    assert plan["summary"]["verification_pgdas_count"] == 1
    assert plan["required_pgdas"][0]["requested_competence"] == "06/2025"
    assert plan["required_pgdas"][0]["request_kind"] == "VERIFICATION"
    assert plan["required_pgdas"][0]["covers_type_01_competences"] == ["06/2025"]
    assert plan["validation"]["status"] == "VALID"


def test_ui_blocks_analysis_when_pgdas_plan_is_incomplete():
    assert "currentPgdasPlanError=plan.validation?.status==='ERROR'" in HTML
    assert "currentMalhaHasCompetences&&((requiredPlan.length===0&&!plan.last_transmitted_competence)||missingMalha.length>0)" in HTML
    assert "planError?'Falha no planejamento'" in HTML
    assert "const documentsComplete=hasMalha&&!planError&&cards.length>0&&received===cards.length" in HTML
    assert "id=\"pgdasPlanNotice\"" in HTML
    assert "VERSÃO 1.45" in HTML
    assert "127.0.0.1:8145" in BATCH
    assert "--port 8145" in BATCH
    assert "127.0.0.1:8145" in DESKTOP
    assert "port=8145" in DESKTOP
    assert "--port 8145" in LINUX
    assert "const noPgdasNeeded=false" in HTML
