from pathlib import Path
from datetime import date
import json

from services.pgdas_planner import calculate_required_pgdas


def load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_aconchego_plan():
    fixture = load_fixture("aconchego")
    plan = calculate_required_pgdas(
        fixture["malha"],
        as_of_date=date(2026, 7, 22),
    )

    assert plan["summary"]["work_month_count"] == 5
    assert plan["summary"]["type_17_month_count"] == 3
    assert plan["summary"]["required_pgdas_count"] == 4

    assert [
        request["requested_competence"]
        for request in plan["required_pgdas"]
    ] == ["06/2022", "06/2023", "11/2025", "06/2026"]

    assert plan["required_pgdas"][2]["covers_type_17_competences"] == [
        "07/2025",
        "08/2025",
    ]
    assert plan["required_pgdas"][3]["request_kind"] == "REFLECTION"
    assert plan["required_pgdas"][3]["requested_competence"] == "06/2026"


def test_almeida_plan():
    fixture = load_fixture("almeida_silva")
    plan = calculate_required_pgdas(
        fixture["malha"],
        as_of_date=date(2026, 7, 22),
    )

    assert plan["summary"]["work_month_count"] == 11
    assert plan["summary"]["type_17_month_count"] == 8
    assert plan["summary"]["required_pgdas_count"] == 5

    assert [
        request["requested_competence"]
        for request in plan["required_pgdas"]
    ] == ["08/2021", "11/2023", "12/2023", "01/2026", "06/2026"]
    assert plan["required_pgdas"][0]["request_kind"] == "VERIFICATION"

    assert plan["required_pgdas"][1]["covers_type_17_competences"] == [
        "02/2022",
        "04/2023",
        "11/2023",
    ]

    assert plan["required_pgdas"][3]["covers_type_17_competences"] == [
        "07/2024",
        "02/2025",
        "09/2025",
        "11/2025",
        "01/2026",
    ]



def test_single_november_2025_requests_june_2026_upfront():
    malha = {
        "contributor": {},
        "work_months": [{
            "competence": "11/2025",
            "types": ["17"],
            "raw_row_count": 1,
            "duplicate_count": 0,
        }],
    }

    plan = calculate_required_pgdas(
        malha,
        as_of_date=date(2026, 7, 22),
    )

    assert [
        request["requested_competence"]
        for request in plan["required_pgdas"]
    ] == ["11/2025", "06/2026"]

    analysis_request = plan["required_pgdas"][0]
    reflection_request = plan["required_pgdas"][1]

    assert analysis_request["request_kind"] == "ANALYSIS"
    assert reflection_request["request_kind"] == "REFLECTION"
    assert reflection_request[
        "covers_reflection_competences"
    ] == [
        "12/2025",
        "01/2026",
        "02/2026",
        "03/2026",
        "04/2026",
        "05/2026",
        "06/2026",
    ]
    assert plan["future_pending_competences"] == [
        "07/2026",
        "08/2026",
        "09/2026",
        "10/2026",
        "11/2026",
    ]


def test_no_posterior_request_before_any_later_period_is_due():
    malha = {
        "contributor": {},
        "work_months": [{
            "competence": "11/2025",
            "types": ["17"],
            "raw_row_count": 1,
            "duplicate_count": 0,
        }],
    }

    plan = calculate_required_pgdas(
        malha,
        as_of_date=date(2025, 12, 10),
    )

    assert [
        request["requested_competence"]
        for request in plan["required_pgdas"]
    ] == ["11/2025"]
