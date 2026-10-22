import pytest

from services.accounting_study import (
    AccountingStudyError,
    EXPOSURE_SCENARIO,
    VALIDATED_SCENARIO,
    apply_study_conclusions,
    build_scenario_confirmations,
    validate_conclusion,
)
from services.analysis_engine import analyze_process


def real_case():
    malha = {
        "work_months": [{
            "competence": "11/2025",
            "types": ["01", "17"],
            "notices": [
                {
                    "type_code": "01",
                    "informed_cents": 0,
                    "considered_cents": 1_664_701,
                    "divergence_cents": 1_664_701,
                },
                {
                    "type_code": "17",
                    "informed_cents": 2_566_600,
                    "considered_cents": 5_503_590,
                    "divergence_cents": 2_936_990,
                },
            ],
        }],
    }
    pgdas = [{
        "source_document": {"file_name": "112025.pdf"},
        "assessment": {
            "period": "11/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 2_566_600},
            },
            "previous_revenues": [],
        },
    }]
    return analyze_process(malha, pgdas)


def conclusion(
    pgdas=2_566_600,
    sped=2_566_600,
    reason="EXTEMPORANEOUS_OTHER_COMPETENCE",
):
    return {
        "competence": "11/2025",
        "validated_pgdas_revenue_cents": pgdas,
        "validated_sped_lfe_revenue_cents": sped,
        "reason_code": reason,
        "notes": "Nota extemporânea de outubro.",
    }


def test_pending_study_keeps_exposure_but_blocks_validated_scenario():
    result = apply_study_conclusions(
        real_case(),
        [],
        [],
    )

    assert result["summary"]["study_pending_count"] == 1
    assert result["summary"]["validated_scenario_ready"] is False
    assert result["summary"][
        "exposure_additional_revenue_cents"
    ] == 2_936_990

    with pytest.raises(AccountingStudyError):
        build_scenario_confirmations(
            result,
            VALIDATED_SCENARIO,
        )


def test_conclusion_preserves_exposure_and_creates_validated_value():
    result = apply_study_conclusions(
        real_case(),
        [],
        [conclusion()],
    )
    regularization = result["analyses"][0][
        "regularization"
    ]

    assert result["summary"]["validated_scenario_ready"] is True
    assert regularization["status"] == "VALIDATED"
    assert regularization[
        "validated_pgdas_revenue_cents"
    ] == 2_566_600
    assert regularization[
        "validated_pgdas_increment_cents"
    ] == 0
    assert regularization[
        "exposure_increment_cents"
    ] == 2_936_990
    assert result["summary"][
        "additional_revenue_reduction_cents"
    ] == 2_936_990


def test_scenarios_generate_different_tax_inputs():
    result = apply_study_conclusions(
        real_case(),
        [],
        [conclusion(pgdas=3_000_000, sped=3_000_000)],
    )

    exposure = build_scenario_confirmations(
        result,
        EXPOSURE_SCENARIO,
    )
    validated = build_scenario_confirmations(
        result,
        VALIDATED_SCENARIO,
    )

    assert exposure[0]["analysis"]["recommendation"][
        "simulation_pgdas_increment_cents"
    ] == 2_936_990
    assert validated[0]["analysis"]["recommendation"][
        "simulation_pgdas_increment_cents"
    ] == 433_400


def test_conclusion_requires_values_for_present_types():
    analysis = apply_study_conclusions(
        real_case(),
        [],
        [],
    )["analyses"][0]

    with pytest.raises(AccountingStudyError):
        validate_conclusion(
            analysis,
            {
                "reason_code": "OTHER",
                "notes": "",
                "validated_pgdas_revenue_cents": None,
                "validated_sped_lfe_revenue_cents": None,
            },
        )



def test_common_accounting_reason_is_accepted():
    result = apply_study_conclusions(
        real_case(),
        [],
        [conclusion(
            reason="CARD_SALE_WITHOUT_INVOICE",
        )],
    )

    assert result["summary"]["study_validated_count"] == 1
    assert result["analyses"][0]["regularization"][
        "reason_code"
    ] == "CARD_SALE_WITHOUT_INVOICE"
