from datetime import date

from services.reflection_coverage import (
    calculate_reflection_coverage,
    latest_normally_due_competence,
)


def confirmation(competence="11/2025", increment=1_000_000):
    return [{
        "decision": "AUTO_APPROVED",
        "analysis": {
            "competence": competence,
            "recommendation": {
                "pgdas_increment_cents": increment,
            },
        },
    }]


def pgdas(period, history):
    return {
        "assessment": {
            "period": period,
            "previous_revenues": [
                {
                    "competence": competence,
                    "total_cents": 1_000_000,
                }
                for competence in history
            ],
            "revenue_summary": {
                "rpa": {"total_cents": 1_000_000},
            },
        },
        "source_document": {"file_name": f"{period}.pdf"},
    }


def months(start, end):
    def index(value):
        month, year = map(int, value.split("/"))
        return year * 12 + month - 1

    def competence(value):
        year, month_zero = divmod(value, 12)
        return f"{month_zero + 1:02d}/{year}"

    return [
        competence(value)
        for value in range(index(start), index(end) + 1)
    ]


def test_latest_due_on_july_22_is_june():
    assert latest_normally_due_competence(
        date(2026, 7, 22)
    ) == "06/2026"


def test_requests_june_2026_after_november_correction():
    primary = pgdas(
        "11/2025",
        months("11/2023", "10/2025"),
    )
    result = calculate_reflection_coverage(
        [primary],
        confirmation(),
        as_of_date=date(2026, 7, 22),
    )

    assert result["closed_months_complete"] is False
    assert result["supplemental_requests"][0][
        "requested_competence"
    ] == "06/2026"
    assert result["actual_calculation_end"] == "06/2026"
    assert result["full_reflection_end"] == "11/2026"
    assert result["future_pending_competences"] == [
        "07/2026",
        "08/2026",
        "09/2026",
        "10/2026",
        "11/2026",
    ]


def test_june_pgdas_completes_closed_months():
    primary = pgdas(
        "11/2025",
        months("11/2023", "10/2025"),
    )
    complement = pgdas(
        "06/2026",
        months("06/2024", "05/2026"),
    )
    result = calculate_reflection_coverage(
        [primary, complement],
        confirmation(),
        as_of_date=date(2026, 7, 22),
    )

    assert result["closed_months_complete"] is True
    assert result["supplemental_requests"] == []
    assert result["status"] == "ACTUAL_COMPLETE_FUTURE_PENDING"


def test_full_horizon_requests_end_month_when_historical():
    primary = pgdas(
        "11/2025",
        months("11/2023", "10/2025"),
    )
    result = calculate_reflection_coverage(
        [primary],
        confirmation(),
        as_of_date=date(2027, 1, 31),
    )

    assert result["supplemental_requests"][0][
        "requested_competence"
    ] == "11/2026"
    assert result["future_pending_competences"] == []
