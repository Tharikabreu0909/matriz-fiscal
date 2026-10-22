import pytest

from services.tax_engine import month_index
from services.tax_segregation import (
    TaxSegregationError,
    category_rate,
    calculate_segmented_reflections,
    factor_r_decision,
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


def confirmation(competence, increment, decision="AUTO_APPROVED"):
    return {
        "competence": competence,
        "decision": decision,
        "analysis": {
            "competence": competence,
            "recommendation": {
                "simulation_pgdas_increment_cents": increment,
                "simulation_pgdas_revenue_cents": None,
            },
        },
    }


def profile(category, competence, increment):
    return {
        "base_distribution": [
            {
                "category": category,
                "basis_points": 10_000,
            }
        ],
        "correction_allocations": [
            {
                "competence": competence,
                "allocations": [
                    {
                        "category": category,
                        "amount_cents": increment,
                    }
                ],
            }
        ],
        "factor_r_payroll": {},
    }


def test_monophase_excludes_pis_and_cofins_from_annex_i():
    normal = category_rate(
        "COMMERCE_NORMAL",
        12_000_000,
        "01/2025",
        None,
    )
    monophase = category_rate(
        "COMMERCE_MONOPHASIC",
        12_000_000,
        "01/2025",
        None,
    )

    assert normal["applicable_rate"] == "0.0400000000"
    assert monophase["applicable_rate"] == "0.0338000000"
    assert monophase["excluded_components"] == [
        "COFINS",
        "PIS",
    ]


def test_icms_st_excludes_icms_share_for_substituted_revenue():
    result = category_rate(
        "COMMERCE_ICMS_ST",
        12_000_000,
        "01/2025",
        None,
    )

    assert result["applicable_rate"] == "0.0264000000"
    assert result["excluded_components"] == ["ICMS"]


def test_combined_monophase_and_icms_st_excludes_both():
    result = category_rate(
        "COMMERCE_MONOPHASIC_ICMS_ST",
        12_000_000,
        "01/2025",
        None,
    )

    assert result["applicable_rate"] == "0.0202000000"


def test_factor_r_selects_annex_iii_at_28_percent():
    decision = factor_r_decision(
        payroll_12m_cents=3_360_000,
        rbt12_cents=12_000_000,
        competence="01/2025",
    )
    below = factor_r_decision(
        payroll_12m_cents=3_359_999,
        rbt12_cents=12_000_000,
        competence="01/2025",
    )

    assert decision["annex"] == "III"
    assert decision["factor_r"] == "0.2800000000"
    assert below["annex"] == "V"


def test_allocation_must_match_correction_exactly():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        1_000_000,
    )
    invalid = profile(
        "COMMERCE_NORMAL",
        "04/2025",
        999_999,
    )

    with pytest.raises(TaxSegregationError):
        calculate_segmented_reflections(
            [pgdas],
            [confirmation("04/2025", 1_000_000)],
            invalid,
        )


def test_segmented_engine_calculates_monophase_direct_difference():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        1_000_000,
    )
    result = calculate_segmented_reflections(
        [pgdas],
        [confirmation("04/2025", 1_000_000)],
        profile(
            "COMMERCE_MONOPHASIC",
            "04/2025",
            1_000_000,
        ),
    )

    april = next(
        row
        for row in result["visible_impacts"]
        if row["competence"] == "04/2025"
    )

    assert april["difference_cents"] == 33_800
    assert april["segments"][0][
        "corrected_annex"
    ] == "I"


def test_validated_decision_is_accepted_by_segmented_engine():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "04/2026",
        1_000_000,
    )
    result = calculate_segmented_reflections(
        [pgdas],
        [
            confirmation(
                "04/2025",
                1_000_000,
                decision="VALIDATED_REGULARIZATION",
            )
        ],
        profile(
            "COMMERCE_NORMAL",
            "04/2025",
            1_000_000,
        ),
        scenario="VALIDATED_REGULARIZATION",
    )

    assert result["summary"][
        "corrected_competence_total_cents"
    ] == 40_000
