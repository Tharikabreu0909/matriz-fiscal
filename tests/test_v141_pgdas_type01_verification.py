from datetime import date

from services.analysis_engine import analyze_process
from services.pgdas_planner import calculate_required_pgdas
from app import calculate_initial_plan_status


def test_type01_only_creates_a_pgdas_verification_request():
    malha = {
        "contributor": {},
        "summary": {"types_found": ["01"]},
        "raw_rows": [],
        "work_months": [{
            "competence": "06/2025",
            "types": ["01"],
            "notices": [{
                "type_code": "01",
                "informed_cents": 0,
                "considered_cents": 1_000_000,
                "divergence_cents": 1_000_000,
            }],
        }],
    }

    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 8, 7))

    assert plan["validation"]["status"] == "VALID"
    assert plan["summary"]["type_17_month_count"] == 0
    assert plan["summary"]["type_01_month_count"] == 1
    assert plan["summary"]["required_pgdas_count"] >= 1
    request = next(
        item for item in plan["required_pgdas"]
        if item["requested_competence"] == "06/2025"
    )
    assert request["request_kind"] == "VERIFICATION"
    assert request["purpose"] == "TYPE_01_DECLARATION_VERIFICATION"
    assert request["covers_type_01_competences"] == ["06/2025"]


def test_type01_verification_is_required_before_initial_documents_are_complete():
    process = {
        "pgdas_plan": {
            "required_pgdas": [{
                "requested_competence": "06/2025",
                "request_kind": "VERIFICATION",
            }]
        }
    }

    missing = calculate_initial_plan_status(process, [])
    assert missing["analysis_requests_complete"] is False
    assert missing["missing_initial_documents"] == ["06/2025"]

    accepted = [{"assessment": {"period": "06/2025"}}]
    complete = calculate_initial_plan_status(process, accepted)
    assert complete["analysis_requests_complete"] is True
    assert complete["missing_initial_documents"] == []


def test_type01_pgdas_check_does_not_trigger_tax_exposure_by_itself():
    malha = {
        "work_months": [{
            "competence": "06/2025",
            "types": ["01"],
            "notices": [{
                "type_code": "01",
                "informed_cents": 0,
                "considered_cents": 1_000_000,
                "divergence_cents": 1_000_000,
            }],
        }]
    }
    pgdas = {
        "source_document": {"file_name": "pgdas-062025.pdf"},
        "assessment": {
            "period": "06/2025",
            "revenue_summary": {"rpa": {"total_cents": 1_000_000}},
            "previous_revenues": [],
        },
    }

    result = analyze_process(malha, [pgdas])
    item = result["analyses"][0]
    assert item["status"] == "AUTO_ANALYZED"
    assert item["recommendation"]["simulation_pgdas_increment_cents"] == 0
    assert item["recommendation"]["calculate_direct_tax"] is False
    assert item["recommendation"]["calculate_rbt12_reflections"] is False
