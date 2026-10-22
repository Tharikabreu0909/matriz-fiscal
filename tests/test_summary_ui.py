from pathlib import Path


def test_ui_has_summary_tabs_and_clear_crossing_labels():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "Resumo da análise" in html
    assert "Análise detalhada" in html
    assert "Memória de cálculo" in html
    assert "Relatório do cliente" in html
    assert (
        "Tipo 01 — SPED/LFE × movimentação de cartão"
        in html
    )
    assert (
        "Tipo 17 — PGDAS × faturamento detectado"
        in html
    )
    assert "Divergência potencial" in html
    assert "Próxima ação" in html



def test_ui_hides_accounting_study_and_uses_single_estimate():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "Conclusão do estudo contábil" not in html
    assert "Estudos pendentes" not in html
    assert 'data-study-save=' not in html
    assert "/api/conclude-accounting-study" not in html
    assert "CONSERVATIVE_FISCAL_EXPOSURE" in html
    assert "VALIDATED_REGULARIZATION" not in html


def test_summary_uses_closed_competence_accordions():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'id="summaryActionCount"' in html
    assert 'id="analysisCompetenceList"' in html
    assert 'class="competence-accordion"' in html
    assert "Ver composição da estimativa" in html
    assert "Abrir análise técnica" in html
    assert "<table class=\"summary-table\">" not in html


def test_tax_screen_uses_progressive_disclosure():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "Estimativa tributária" in html
    assert 'id="technicalCalculationDetails"' in html
    assert "Memória técnica e reflexos por competência" in html
    assert 'class="compact-summary-grid"' in html


def test_ui_removes_special_tax_adjustments():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "PIS monofásico" not in html
    assert "Cofins monofásica" not in html
    assert "ICMS-ST" not in html
    assert "Fator R" not in html
    assert "Ajustes tributários avançados" not in html
    assert "SIMPLE_TAX_PROFILE_V3" not in html



def test_ui_has_company_portfolio_and_single_annex_estimate():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "Carteira de empresas" in html
    assert 'id="companyGrid"' in html
    assert 'id="companyForm"' in html
    assert "Histórico do processo" in html
    assert 'id="taxAnnex"' in html
    assert "O cálculo completo acontece em um único clique." in html
    assert "Ajustes tributários avançados" not in html
    assert "Distribuição dos anexos" not in html
    assert "PIS monofásico" not in html
    assert "ICMS-ST" not in html


def test_professional_design_shell_is_connected_to_real_portfolio():
    html = (
        Path(__file__).resolve().parents[1] / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'class="app-shell"' in html
    assert 'class="sidebar"' in html
    assert 'id="dashboardPage"' in html
    assert 'id="companyGrid"' in html
    assert 'id="malhaCompanyGrid"' in html
    assert 'id="reportCompanyGrid"' in html
    assert 'id="globalHistoryList"' in html
    assert "Aconchego da Moda Ltda." not in html
    assert "312" not in html
    assert 'data-workflow-step="malha"' in html
    assert "VERSÃO 1.41" in html



def test_guided_journey_has_separate_screens_and_progress():
    html = (
        Path(__file__).resolve().parents[1] / "static" / "index.html"
    ).read_text(encoding="utf-8")
    for step in ["malha", "documents", "analysis", "calculation", "report", "history"]:
        assert f'data-workflow-step="{step}"' in html
        assert f'data-workflow-screen="{step}"' in html
    assert 'id="bulkPgdasDropzone"' in html
    assert 'id="bulkPgdasInput"' in html
    assert 'multiple' in html
    assert 'id="documentProgressList"' not in html
    assert "Jogue os arquivos PGDAS aqui" in html
    assert "Etapa 1 de 5" in html
    assert "Etapa 5 de 5" in html


def test_malha_competences_are_vertical_expandable_lines():
    html = (
        Path(__file__).resolve().parents[1] / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'class="malha-competence-row"' in html
    assert 'class="malha-notice-stack"' in html
    assert "SPED/LFE × movimentação detectada" in html
    assert "PGDAS × faturamento detectado" in html
    assert "malha-notice-line" in html


def test_v127_refines_company_documents_analysis_and_calculation():
    html=(Path(__file__).resolve().parents[1]/"static"/"index.html").read_text(encoding="utf-8")
    assert "Dados principais" in html
    assert "CFDF / Inscrição estadual" in html
    assert "Jogue os arquivos PGDAS aqui" in html
    assert 'class="pgdas-card-status"' in html
    assert "Lendo arquivo" in html
    assert "Concluído" in html
    assert "analysis-empty-state" in html
    assert 'id="estimateSummaryPanel"' in html
    assert "Resumo da estimativa" in html
