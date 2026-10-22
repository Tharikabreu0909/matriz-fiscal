from services.client_report import (
    build_report_model,
    render_client_report,
)


def fixtures():
    process = {
        "company_name": "Empresa <Teste> & Filhos",
        "company_cnpj": "10689433000150",
        "company_identifier": "07.123.456/001-00",
    }
    analysis_result = {
        "analyses": [{
            "competence": "04/2025",
            "segregation": {
                "type_01": {
                    "present": True,
                    "minimum_gap_cents": 2_000_000,
                    "minimum_detected_cents": 5_000_000,
                    "recommended_target_cents": None,
                },
                "type_17": {
                    "present": True,
                    "simulation_increment_cents": 1_500_000,
                    "simulation_target_cents": 5_500_000,
                    "recommended_target_cents": None,
                },
                "accounting_study": {
                    "status": "PENDING_ACCOUNTING_STUDY",
                },
                "consolidated": {
                    "sped_lfe_target_cents": None,
                    "pgdas_target_cents": None,
                    "simulation_tax_base_increment_cents": 1_500_000,
                    "tax_base_increment_cents": 1_500_000,
                },
            },
        }],
    }
    tax_result = {
        "configuration": {"annex": "I"},
        "summary": {
            "corrected_competence_total_cents": 100_000,
            "reflection_total_cents": 20_000,
            "impacted_month_count": 2,
            "calculation_end_competence": "06/2026",
            "full_reflection_end_competence": "11/2026",
            "future_pending_count": 5,
            "is_partial": True,
        },
        "visible_impacts": [
            {
                "competence": "04/2025",
                "classification": "CORRECTED_COMPETENCE",
                "difference_cents": 100_000,
            },
            {
                "competence": "05/2025",
                "classification": "RBT12_REFLECTION",
                "difference_cents": 20_000,
            },
        ],
        "warnings": [],
    }
    charges = {
        "source": {"update_date": "2026-04-10"},
        "summary": {
            "principal_cents": 120_000,
            "fine_cents": 24_000,
            "interest_cents": 4_800,
            "total_cents": 148_800,
        },
        "rows": [{
            "competence": "04/2025",
            "principal_cents": 100_000,
            "fine_cents": 20_000,
            "interest_cents": 4_000,
            "total_cents": 124_000,
        }],
        "warnings": [],
    }
    return process, analysis_result, tax_result, charges


def test_report_keeps_type_actions_separate():
    process, analysis, tax, charges = fixtures()
    model = build_report_model(
        process,
        analysis,
        [],
        tax,
        charges,
    )
    row = model["competence_rows"][0]

    assert row["tax_increment_cents"] == 1_500_000
    assert row["tax_increment_cents"] != 3_500_000
    assert len(row["actions"]) == 2
    assert "SPED/LFE" in row["actions"][0]
    assert "PGDAS" in row["actions"][1]


def test_report_uses_updated_total():
    process, analysis, tax, charges = fixtures()
    model = build_report_model(
        process,
        analysis,
        [],
        tax,
        charges,
    )

    assert model["summary"]["updated_total_cents"] == 148_800
    assert model["update_date"] == "10/04/2026"


def test_report_html_is_client_friendly_and_escaped():
    process, analysis, tax, charges = fixtures()
    model = build_report_model(
        process,
        analysis,
        [],
        tax,
        charges,
    )
    html = render_client_report(model)

    assert "Empresa &lt;Teste&gt; &amp; Filhos" in html
    assert "Imprimir ou salvar em PDF" in html
    assert "Pontos de atenção" in html
    assert "Exposição total estimada" in html
    assert "Não constitui ordem automática de retificação" in html
    assert "source_consistency" not in html
    assert "requires_review" not in html



def test_partial_report_explains_future_pgdas():
    process, analysis, tax, charges = fixtures()
    model = build_report_model(
        process,
        analysis,
        [],
        tax,
        charges,
    )
    html = render_client_report(model)

    assert "Resultado parcial até 06/2026" in html
    assert "até 11/2026" in html



def test_report_does_not_order_exact_sped_or_pgdas_rectification():
    process, analysis, tax, charges = fixtures()
    model = build_report_model(
        process,
        analysis,
        [],
        tax,
        charges,
    )
    html = render_client_report(model)

    assert "Retificar o SPED/LFE para" not in html
    assert "Retificar o PGDAS para" not in html
    assert (
        "O cruzamento detectou movimentação mínima"
        in html
    )
    assert (
        "Exposição simulada considerando receita"
        in html
    )
