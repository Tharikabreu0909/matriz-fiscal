import pytest

from services.annex_columns_profile import (
    AnnexColumnsError,
    PROFILE_CODE,
    build_revenue_lines_profile,
)


def setup_month(
    original=1_521_600,
    additional=774_500,
):
    return {
        "months": [
            {
                "competence": "01/2025",
                "available": True,
                "original_revenue_cents": original,
                "additional_revenue_cents": additional,
                "corrected_revenue_cents": original + additional,
            }
        ]
    }


def profile(
    declared_annexes,
    rectified_annexes,
    declared,
    divergence,
    same_annexes=False,
):
    return {
        "version": PROFILE_CODE,
        "declared_annexes": declared_annexes,
        "rectified_annexes": rectified_annexes,
        "same_annexes": same_annexes,
        "monthly_allocations": [
            {
                "competence": "01/2025",
                "declared": declared,
                "divergence": divergence,
            }
        ],
    }


def test_single_annex_uses_all_declared_and_divergent_revenue():
    generated = build_revenue_lines_profile(
        profile(
            ["I"],
            ["I"],
            {"I": 1_521_600},
            {"I": 774_500},
            same_annexes=True,
        ),
        setup_month(),
    )

    month = generated["monthly_allocations"][0]
    assert month["original_lines"] == [
        {
            "amount_cents": 1_521_600,
            "activity": "I",
            "pis_monophase": False,
            "cofins_monophase": False,
            "icms_st": False,
        }
    ]
    assert month["additional_lines"][0]["amount_cents"] == 774_500


def test_columns_split_divergence_5000_and_2745():
    generated = build_revenue_lines_profile(
        profile(
            ["I", "III"],
            ["I", "III"],
            {"I": 1_000_000, "III": 521_600},
            {"I": 500_000, "III": 274_500},
        ),
        setup_month(),
    )

    month = generated["monthly_allocations"][0]
    assert [
        (line["activity"], line["amount_cents"])
        for line in month["original_lines"]
    ] == [("I", 1_000_000), ("III", 521_600)]
    assert [
        (line["activity"], line["amount_cents"])
        for line in month["additional_lines"]
    ] == [("I", 500_000), ("III", 274_500)]


def test_declared_and_rectified_can_use_different_annexes():
    generated = build_revenue_lines_profile(
        profile(
            ["I"],
            ["III", "V"],
            {"I": 1_521_600},
            {"III": 500_000, "V": 274_500},
        ),
        setup_month(),
    )

    assert generated["options"]["enabled_activities"] == [
        "I",
        "III",
        "V",
    ]
    assert generated["monthly_allocations"][0][
        "additional_lines"
    ][1]["activity"] == "V"


def test_same_annexes_ignores_separate_rectified_selection():
    generated = build_revenue_lines_profile(
        profile(
            ["II"],
            ["V"],
            {"II": 1_521_600},
            {"II": 774_500},
            same_annexes=True,
        ),
        setup_month(),
    )

    assert generated["options"]["enabled_activities"] == ["II"]


def test_distribution_must_close_exactly():
    with pytest.raises(AnnexColumnsError):
        build_revenue_lines_profile(
            profile(
                ["I", "III"],
                ["I", "III"],
                {"I": 1_000_000, "III": 500_000},
                {"I": 500_000, "III": 274_500},
            ),
            setup_month(),
        )


def test_negative_automatic_balance_is_blocked():
    with pytest.raises(AnnexColumnsError):
        build_revenue_lines_profile(
            profile(
                ["I", "III"],
                ["I", "III"],
                {"I": 1_600_000, "III": -78_400},
                {"I": 500_000, "III": 274_500},
            ),
            setup_month(),
        )


def _month_index(competence):
    month, year = map(int, competence.split("/"))
    return year * 12 + month - 1


def _competence_from_index(index):
    year, month_zero = divmod(index, 12)
    return f"{month_zero + 1:02d}/{year}"


def _pgdas_with_timeline(start, end, monthly_cents):
    rows = [
        {
            "competence": _competence_from_index(index),
            "total_cents": monthly_cents,
        }
        for index in range(_month_index(start), _month_index(end))
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


def _confirmation(competence, increment):
    return {
        "competence": competence,
        "decision": "AUTO_APPROVED",
        "analysis": {
            "competence": competence,
            "recommendation": {
                "simulation_pgdas_increment_cents": increment,
                "simulation_pgdas_revenue_cents": None,
            },
        },
    }


def test_full_estimate_uses_declared_and_divergence_columns():
    from services.annex_columns_profile import (
        calculate_annex_columns_reflections,
    )

    pgdas = _pgdas_with_timeline(
        "01/2024",
        "01/2025",
        1_000_000,
    )
    tax_setup = {
        "months": [
            {
                "competence": "01/2025",
                "available": True,
                "original_revenue_cents": 1_000_000,
                "additional_revenue_cents": 500_000,
                "corrected_revenue_cents": 1_500_000,
            }
        ]
    }
    result = calculate_annex_columns_reflections(
        pgdas_documents=[pgdas],
        confirmations=[_confirmation("01/2025", 500_000)],
        profile=profile(
            ["I", "III"],
            ["I", "III"],
            {"I": 700_000, "III": 300_000},
            {"I": 200_000, "III": 300_000},
        ),
        tax_setup=tax_setup,
        calculation_end_competence="01/2025",
    )

    january = result["visible_impacts"][0]
    assert january["competence"] == "01/2025"
    assert {
        segment["corrected_annex"]
        for segment in january["segments"]
    } == {"I", "III"}
    assert result["configuration"]["profile"] == PROFILE_CODE


def test_annex_v_is_calculated_directly_without_factor_r():
    from services.tax_revenue_lines import line_rate

    rate = line_rate(
        {
            "amount_cents": 1_000_000,
            "activity": "V",
            "pis_monophase": False,
            "cofins_monophase": False,
            "icms_st": False,
        },
        12_000_000,
        "01/2025",
        None,
    )

    assert rate["annex"] == "V"
    assert rate["factor_r"] is None
