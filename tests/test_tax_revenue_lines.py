import pytest

from services.accounting_study import (
    VALIDATED_SCENARIO,
)
from services.tax_engine import month_index
from services.tax_revenue_lines import (
    RevenueLinesError,
    build_tax_setup,
    calculate_revenue_line_reflections,
    line_rate,
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
        "source_document": {
            "file_name": "timeline.pdf",
        },
        "assessment": {
            "period": end,
            "revenue_summary": {
                "rpa": {
                    "total_cents": monthly_cents,
                },
            },
            "previous_revenues": rows,
        },
    }


def confirmation(
    competence,
    increment,
    decision="AUTO_APPROVED",
):
    return {
        "competence": competence,
        "decision": decision,
        "analysis": {
            "competence": competence,
            "recommendation": {
                "simulation_pgdas_increment_cents": (
                    increment
                ),
                "simulation_pgdas_revenue_cents": None,
            },
        },
    }


def normal_line(amount, **overrides):
    line = {
        "amount_cents": amount,
        "activity": "I",
        "pis_monophase": False,
        "cofins_monophase": False,
        "icms_st": False,
    }
    line.update(overrides)
    return line


def profile_for_month(
    competence,
    original,
    additional,
    original_lines=None,
    additional_lines=None,
    activities=None,
    treatments=None,
    payroll=None,
):
    return {
        "version": "REVENUE_LINES_V2",
        "options": {
            "enabled_activities": (
                activities or ["I"]
            ),
            "enabled_treatments": (
                treatments or []
            ),
        },
        "monthly_allocations": [
            {
                "competence": competence,
                "original_lines": (
                    original_lines
                    if original_lines is not None
                    else [normal_line(original)]
                ),
                "additional_lines": (
                    additional_lines
                    if additional_lines is not None
                    else [normal_line(additional)]
                ),
            }
        ],
        "factor_r_payroll": payroll or {},
    }


def test_pis_and_cofins_can_be_marked_separately():
    pis = line_rate(
        normal_line(
            1_000_000,
            pis_monophase=True,
        ),
        12_000_000,
        "01/2025",
        None,
    )
    cofins = line_rate(
        normal_line(
            1_000_000,
            cofins_monophase=True,
        ),
        12_000_000,
        "01/2025",
        None,
    )
    both = line_rate(
        normal_line(
            1_000_000,
            pis_monophase=True,
            cofins_monophase=True,
        ),
        12_000_000,
        "01/2025",
        None,
    )

    assert pis["applicable_rate"] == "0.0388960000"
    assert cofins["applicable_rate"] == "0.0349040000"
    assert both["applicable_rate"] == "0.0338000000"


def test_same_line_can_combine_monophase_and_icms_st():
    result = line_rate(
        normal_line(
            1_000_000,
            pis_monophase=True,
            cofins_monophase=True,
            icms_st=True,
        ),
        12_000_000,
        "01/2025",
        None,
    )

    assert result["applicable_rate"] == "0.0202000000"
    assert result["excluded_components"] == [
        "PIS",
        "COFINS",
        "ICMS",
    ]


def test_treatments_are_limited_to_enabled_switches():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2025",
        2_296_100,
    )
    profile = profile_for_month(
        "01/2025",
        2_296_100,
        1_000_000,
        original_lines=[
            normal_line(
                1_296_100,
            ),
            normal_line(
                1_000_000,
                pis_monophase=True,
            ),
        ],
        additional_lines=[
            normal_line(1_000_000),
        ],
        treatments=[],
    )

    with pytest.raises(RevenueLinesError):
        calculate_revenue_line_reflections(
            [pgdas],
            [confirmation("01/2025", 1_000_000)],
            profile,
            calculation_end_competence="01/2025",
        )


def test_month_original_total_must_close_exactly():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2025",
        2_296_100,
    )
    profile = profile_for_month(
        "01/2025",
        2_296_100,
        1_000_000,
        original_lines=[
            normal_line(2_000_000),
        ],
    )

    with pytest.raises(RevenueLinesError):
        calculate_revenue_line_reflections(
            [pgdas],
            [confirmation("01/2025", 1_000_000)],
            profile,
            calculation_end_competence="01/2025",
        )


def test_month_can_split_22961_into_normal_and_monophase():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2025",
        2_296_100,
    )
    profile = profile_for_month(
        "01/2025",
        2_296_100,
        1_000_000,
        original_lines=[
            normal_line(1_296_100),
            normal_line(
                1_000_000,
                pis_monophase=True,
                cofins_monophase=True,
            ),
        ],
        additional_lines=[
            normal_line(1_000_000),
        ],
        treatments=[
            "PIS_MONOPHASIC",
            "COFINS_MONOPHASIC",
        ],
    )
    result = calculate_revenue_line_reflections(
        [pgdas],
        [confirmation("01/2025", 1_000_000)],
        profile,
        calculation_end_competence="01/2025",
    )
    january = result["visible_impacts"][0]

    assert january["original_revenue_cents"] == 2_296_100
    assert len(january["segments"]) == 2
    assert any(
        "PIS monofásico" in segment["category_label"]
        for segment in january["segments"]
    )


def test_factor_r_switch_opens_annex_decision_in_engine():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2025",
        1_000_000,
    )
    profile = profile_for_month(
        "01/2025",
        1_000_000,
        1_000_000,
        original_lines=[
            {
                **normal_line(1_000_000),
                "activity": "FACTOR_R",
            }
        ],
        additional_lines=[
            {
                **normal_line(1_000_000),
                "activity": "FACTOR_R",
            }
        ],
        activities=["FACTOR_R"],
        payroll={
            "01/2025": 3_360_000,
        },
    )
    result = calculate_revenue_line_reflections(
        [pgdas],
        [confirmation("01/2025", 1_000_000)],
        profile,
        calculation_end_competence="01/2025",
    )

    assert result["factor_r_decisions"][0][
        "annex"
    ] == "III"


def test_tax_setup_returns_real_month_revenue_and_increment():
    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2025",
        2_296_100,
    )
    setup = build_tax_setup(
        [pgdas],
        [confirmation("01/2025", 1_000_000)],
        calculation_end_competence="01/2025",
        full_reflection_end_competence="01/2026",
        future_pending_competences=[],
        scenario=VALIDATED_SCENARIO,
    )

    assert setup["months"] == [
        {
            "competence": "01/2025",
            "available": True,
            "original_revenue_cents": 2_296_100,
            "additional_revenue_cents": 1_000_000,
            "corrected_revenue_cents": 3_296_100,
            "source": "CURRENT_ASSESSMENT",
            "source_file": "timeline.pdf",
        }
    ]


def test_validated_confirmation_is_used_by_reflection_coverage():
    from services.reflection_coverage import (
        calculate_reflection_coverage,
    )

    pgdas = pgdas_with_timeline(
        "01/2024",
        "01/2026",
        1_000_000,
    )
    result = calculate_reflection_coverage(
        [pgdas],
        [
            confirmation(
                "01/2025",
                1_000_000,
                decision="VALIDATED_REGULARIZATION",
            )
        ],
    )

    assert result["correction_competences"] == [
        "01/2025"
    ]
