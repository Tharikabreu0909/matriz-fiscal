"""Janela real de histórico do PGDAS-D (dados 100% sintéticos)."""
from datetime import date

from services.pgdas_planner import calculate_required_pgdas


def _notice(code):
    return {"type_code": code, "informed_cents": 0,
            "considered_cents": 100_000, "divergence_cents": 100_000}


def _malha(types_by_competence):
    return {
        "contributor": {"legal_name": "Empresa Sintetica", "cfdf": "1"},
        "source_document": {"file_name": "malha.pdf"},
        "work_months": [
            {"competence": comp, "notices": [_notice(code) for code in codes]}
            for comp, codes in types_by_competence.items()
        ],
    }


def test_history_window_starts_in_january_of_previous_year():
    from services.pgdas_planner import history_window
    assert history_window("04/2026") == ("01/2025", "04/2026")
    assert history_window("01/2026") == ("01/2025", "01/2026")
    assert history_window("12/2025") == ("01/2024", "12/2025")


def test_plan_asks_for_pgdas_that_covers_months_before_short_history():
    malha = _malha({
        "06/2025": ["01"], "07/2025": ["17"], "08/2025": ["17"],
        "11/2025": ["17"], "03/2026": ["01"], "04/2026": ["17"],
    })
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 5, 10))
    requests = {r["requested_competence"]: r for r in plan["required_pgdas"]}

    # janela de 04/2026 começa em 01/2025 (e não em 04/2024, como se supunha)
    assert requests["04/2026"]["coverage_start"] == "01/2025"
    # os 12 meses anteriores a 06/2025 (06/2024..12/2024) precisam de um PGDAS próprio
    assert "06/2025" in requests
    assert requests["06/2025"]["coverage_start"] == "01/2024"
    assert plan["validation"]["status"] == "VALID"


def test_plan_does_not_add_request_when_history_already_covers_everything():
    malha = _malha({"02/2026": ["17"], "03/2026": ["17"]})
    plan = calculate_required_pgdas(malha, as_of_date=date(2026, 5, 10))
    periods = [r["requested_competence"] for r in plan["required_pgdas"]
               if r["request_kind"] != "REFLECTION"]
    assert periods == ["03/2026"]
