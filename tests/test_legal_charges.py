from datetime import date
from decimal import Decimal

from services.legal_charges import (
    calculate_legal_charges,
    fine_rate,
    interest_rate,
    standard_due_date,
)


def tax_result():
    return {
        "visible_impacts": [
            {
                "competence": "11/2025",
                "classification": "CORRECTED_COMPETENCE",
                "difference_cents": 100_000,
            },
            {
                "competence": "12/2025",
                "classification": "RBT12_REFLECTION",
                "difference_cents": 50_000,
            },
        ]
    }


def pgdas():
    return [{
        "assessment": {"period": "11/2025"},
        "das": {"due_date": "22/12/2025"},
    }]


def rates():
    return {
        "2026-01": Decimal("1.00"),
        "2026-02": Decimal("0.90"),
        "2026-03": Decimal("1.10"),
    }


def test_standard_due_date_moves_weekend_forward():
    assert standard_due_date("11/2025") == date(2025, 12, 22)


def test_fine_is_limited_to_twenty_percent():
    assert fine_rate(10) == Decimal("0.0330")
    assert fine_rate(100) == Decimal("0.20")


def test_interest_same_month_is_zero():
    assert interest_rate(
        date(2026, 4, 20),
        date(2026, 4, 30),
        {},
    ) == Decimal("0")


def test_interest_next_month_is_one_percent():
    assert interest_rate(
        date(2026, 3, 20),
        date(2026, 4, 1),
        {},
    ) == Decimal("0.01")


def test_interest_sums_selic_and_payment_month():
    assert interest_rate(
        date(2025, 12, 22),
        date(2026, 4, 10),
        rates(),
    ) == Decimal("0.0400")


def test_calculate_legal_charges():
    result = calculate_legal_charges(
        tax_result=tax_result(),
        pgdas_documents=pgdas(),
        update_date_text="2026-04-10",
        monthly_selic=rates(),
    )

    first = result["rows"][0]
    second = result["rows"][1]

    assert first["due_date"] == "2025-12-22"
    assert first["due_date_source"] == "PGDAS_DOCUMENT"
    assert first["fine_cents"] == 20_000
    assert first["interest_cents"] == 4_000
    assert first["total_cents"] == 124_000

    assert second["due_date_source"] == "STANDARD_ESTIMATE"
    assert result["summary"]["estimated_due_date_count"] == 1
    assert result["summary"]["principal_cents"] == 150_000
