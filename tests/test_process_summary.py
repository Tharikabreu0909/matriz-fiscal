from services.analysis_engine import analyze_process
from services.process_summary import build_process_summary


def real_case_analysis():
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
        "source_document": {
            "file_name": "pgdas-112025.pdf",
        },
        "assessment": {
            "period": "11/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 2_566_600},
            },
            "previous_revenues": [],
        },
    }]
    return analyze_process(malha, pgdas)


def test_summary_shows_clear_crossing_names_and_divergences():
    summary = build_process_summary(
        real_case_analysis()
    )

    assert summary["metrics"]["competence_count"] == 1
    assert summary["metrics"][
        "exposure_competence_count"
    ] == 1
    assert summary["metrics"][
        "accounting_study_count"
    ] == 1
    assert summary["financial"][
        "additional_revenue_cents"
    ] == 2_936_990

    type_01, type_17 = summary["rows"]

    assert type_01["crossing_label"] == (
        "SPED/LFE × movimentação de cartão"
    )
    assert type_01["divergence_cents"] == 1_664_701
    assert type_01["status"] == "ACCOUNTING_STUDY"

    assert type_17["crossing_label"] == (
        "PGDAS × faturamento fiscal detectado"
    )
    assert type_17["divergence_cents"] == 2_936_990
    assert type_17[
        "simulation_target_cents"
    ] == 5_503_590


def test_summary_financial_values_evolve_by_stage():
    analysis = real_case_analysis()
    tax = {
        "summary": {
            "corrected_competence_total_cents": 100_000,
            "reflection_total_cents": 25_000,
        }
    }
    charges = {
        "summary": {
            "principal_cents": 125_000,
            "fine_cents": 25_000,
            "interest_cents": 5_000,
            "total_cents": 155_000,
        }
    }

    before = build_process_summary(analysis)
    after_tax = build_process_summary(
        analysis,
        tax_result=tax,
    )
    complete = build_process_summary(
        analysis,
        tax_result=tax,
        legal_charges=charges,
    )

    assert before["financial"]["direct_tax_cents"] == 0
    assert after_tax["financial"]["direct_tax_cents"] == 100_000
    assert after_tax["financial"]["reflection_tax_cents"] == 25_000
    assert complete["financial"]["charges_cents"] == 30_000
    assert complete["financial"]["updated_total_cents"] == 155_000



def test_summary_compares_exposure_and_validated_regularization():
    from services.accounting_study import apply_study_conclusions

    analysis = real_case_analysis()
    regularization = apply_study_conclusions(
        analysis,
        [],
        [{
            "competence": "11/2025",
            "validated_pgdas_revenue_cents": 2_566_600,
            "validated_sped_lfe_revenue_cents": 2_566_600,
            "reason_code": "EXTEMPORANEOUS_OTHER_COMPETENCE",
            "notes": "Nota de outubro.",
        }],
    )
    exposure_tax = {
        "summary": {
            "corrected_competence_total_cents": 100_000,
            "reflection_total_cents": 20_000,
        }
    }
    validated_tax = {
        "summary": {
            "corrected_competence_total_cents": 0,
            "reflection_total_cents": 0,
        }
    }

    result = build_process_summary(
        analysis,
        regularization_result=regularization,
        tax_result=exposure_tax,
        validated_tax_result=validated_tax,
    )

    assert result["metrics"]["study_validated_count"] == 1
    assert result["metrics"]["validated_scenario_ready"] is True
    assert result["rows"][0]["validated_cents"] == 2_566_600
    assert result["validated_financial"][
        "additional_revenue_cents"
    ] == 0



def test_summary_groups_type_01_and_17_in_one_competence():
    summary = build_process_summary(
        real_case_analysis()
    )

    assert summary["metrics"][
        "action_competence_count"
    ] == 1
    assert len(summary["competences"]) == 1

    month = summary["competences"][0]
    assert month["competence"] == "11/2025"
    assert month["types"] == ["01", "17"]
    assert len(month["crossings"]) == 2
    assert month["primary_divergence_cents"] == 2_936_990
    assert month["next_action"] == "Concluir estudo contábil"
