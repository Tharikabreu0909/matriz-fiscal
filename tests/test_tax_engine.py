from services.tax_engine import (
    calculate_hidden_reflections,
    effective_rate,
    month_index,
)


def competence_from_index(index):
    year, month_zero = divmod(index, 12)
    return f"{month_zero + 1:02d}/{year}"


def pgdas_with_timeline(start, end, monthly_cents):
    start_index = month_index(start)
    end_index = month_index(end)
    rows = [
        {
            "competence": competence_from_index(index),
            "total_cents": monthly_cents,
        }
        for index in range(start_index, end_index)
    ]
    return {
        "source_document": {"file_name": "timeline.pdf"},
        "assessment": {
            "period": end,
            "revenue_summary": {
                "rpa": {"total_cents": monthly_cents},
            },
            "previous_revenues": rows,
        },
    }


def confirmation(competence, increment):
    return {
        "competence": competence,
        "decision": "CONFIRMED",
        "analysis": {
            "competence": competence,
            "recommendation": {
                "pgdas_increment_cents": increment,
                "corrected_pgdas_revenue_cents": None,
            },
        },
    }


def test_annex_i_effective_rate():
    result = effective_rate(33_702_189, "I")
    assert result["bracket"] == 2
    assert result["effective_rate"].startswith("0.055375")


def test_correction_without_rate_reflection():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        1_000_000,
    )
    result = calculate_hidden_reflections(
        [pgdas],
        [confirmation("04/2025", 1_000_000)],
        "I",
        True,
    )

    april = next(
        row
        for row in result["visible_impacts"]
        if row["competence"] == "04/2025"
    )
    assert april["difference_cents"] == 40_000
    assert result["summary"]["reflection_total_cents"] == 0


def test_reflection_changes_rate():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        3_000_000,
    )
    result = calculate_hidden_reflections(
        [pgdas],
        [confirmation("04/2025", 1_000_000)],
        "I",
        True,
    )

    may = next(
        row
        for row in result["visible_impacts"]
        if row["competence"] == "05/2025"
    )
    assert may["classification"] == "RBT12_REFLECTION"
    assert may["corrected_rbt12_cents"] == 37_000_000
    assert may["difference_cents"] > 0


def test_correction_affects_exactly_twelve_following_months():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "05/2026",
        3_000_000,
    )
    result = calculate_hidden_reflections(
        [pgdas],
        [confirmation("04/2025", 1_000_000)],
        "I",
        True,
    )

    april_2026 = next(
        row
        for row in result["hidden_timeline"]
        if row["competence"] == "04/2026"
    )
    assert april_2026["corrected_rbt12_cents"] == (
        april_2026["original_rbt12_cents"] + 1_000_000
    )

    assert all(
        row["competence"] != "05/2026"
        for row in result["hidden_timeline"]
    )


def test_2027_is_blocked():
    pgdas = pgdas_with_timeline(
        "01/2025",
        "12/2026",
        2_000_000,
    )
    result = calculate_hidden_reflections(
        [pgdas],
        [confirmation("12/2026", 500_000)],
        "I",
        True,
    )
    assert result["summary"]["unsupported_month_count"] == 12



def test_tax_engine_ignores_type_01_increment():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        3_000_000,
    )
    confirmed_analysis = {
        "competence": "04/2025",
        "decision": "CONFIRMED",
        "analysis": {
            "competence": "04/2025",
            "recommendation": {
                "sped_increment_cents": 9_000_000,
                "pgdas_increment_cents": 1_000_000,
                "corrected_pgdas_revenue_cents": 4_000_000,
            },
            "segregation": {
                "consolidated": {
                    "tax_base_increment_cents": 1_000_000,
                    "calculation_rule": (
                        "DO_NOT_SUM_TYPE_01_AND_TYPE_17"
                    ),
                    "tax_source": "TYPE_17_ONLY",
                },
            },
        },
    }

    result = calculate_hidden_reflections(
        [pgdas],
        [confirmed_analysis],
        "I",
        True,
    )

    april = next(
        row
        for row in result["hidden_timeline"]
        if row["competence"] == "04/2025"
    )
    assert april["revenue_increment_cents"] == 1_000_000



def test_tax_engine_accepts_automatic_decision():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        3_000_000,
    )
    automatic = {
        "competence": "04/2025",
        "decision": "AUTO_APPROVED",
        "analysis": {
            "competence": "04/2025",
            "recommendation": {
                "pgdas_increment_cents": 1_000_000,
                "corrected_pgdas_revenue_cents": 4_000_000,
            },
        },
    }

    result = calculate_hidden_reflections(
        [pgdas],
        [automatic],
        "I",
        True,
    )

    april = next(
        row
        for row in result["hidden_timeline"]
        if row["competence"] == "04/2025"
    )
    assert april["revenue_increment_cents"] == 1_000_000



def test_tax_engine_stops_at_actual_available_month():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "06/2026",
        3_000_000,
    )
    result = calculate_hidden_reflections(
        [pgdas],
        [confirmation("11/2025", 1_000_000)],
        "I",
        True,
        calculation_end_competence="06/2026",
        full_reflection_end_competence="11/2026",
        future_pending_competences=[
            "07/2026",
            "08/2026",
            "09/2026",
            "10/2026",
            "11/2026",
        ],
    )

    assert result["summary"]["is_partial"] is True
    assert result["summary"][
        "calculation_end_competence"
    ] == "06/2026"
    assert result["summary"][
        "full_reflection_end_competence"
    ] == "11/2026"
    assert result["hidden_timeline"][-1][
        "competence"
    ] == "06/2026"



def test_tax_engine_prefers_simulation_increment():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        3_000_000,
    )
    automatic = {
        "competence": "04/2025",
        "decision": "AUTO_APPROVED",
        "analysis": {
            "competence": "04/2025",
            "recommendation": {
                "pgdas_increment_cents": 9_000_000,
                "simulation_pgdas_increment_cents": 1_000_000,
                "corrected_pgdas_revenue_cents": 12_000_000,
                "simulation_pgdas_revenue_cents": 4_000_000,
            },
        },
    }

    result = calculate_hidden_reflections(
        [pgdas],
        [automatic],
        "I",
        True,
    )

    april = next(
        row
        for row in result["hidden_timeline"]
        if row["competence"] == "04/2025"
    )

    assert april["revenue_increment_cents"] == 1_000_000
    assert result["configuration"]["scenario"] == (
        "CONSERVATIVE_FISCAL_EXPOSURE"
    )
