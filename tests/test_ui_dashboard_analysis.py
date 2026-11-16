from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")


def test_dashboard_has_exactly_the_four_requested_cards():
    section = HTML.split('<section class="dashboard-kpis">')[1].split("</section>")[0]
    assert section.count('class="dashboard-kpi"') == 4
    for label in ("Empresas", "Saudáveis", "Malhas ativas", "Relatório gerado"):
        assert f"<span>{label}</span>" in section
    assert "Em análise" not in section


def test_dashboard_has_no_regularization_concept():
    dashboard = HTML.split('id="dashboardPage"')[1].split('id="portfolioView"')[0]
    assert "regulariza" not in dashboard.lower()


def test_dashboard_ranking_is_sorted_by_exposure_desc():
    assert "b.exposure_estimated_cents - a.exposure_estimated_cents" in HTML
    assert 'id="dashboardRanking"' in HTML


def test_analysis_has_single_competence_list_with_type_badges():
    assert 'id="diagnosticList"' not in HTML
    assert 'id="analysisCompetenceList"' in HTML
    assert "type-badge t${type}" in HTML and "Tipo ${type}" in HTML
    assert "A calcular" in HTML and "DAS corrigido" in HTML
    assert "name=\"competences\"" in HTML  # uma competência aberta por vez


def test_dashboard_dropped_recent_movements_and_portfolio_is_a_table():
    assert 'id="dashboardRecent"' not in HTML
    assert "Movimentações recentes" not in HTML
    assert "function companyRow" in HTML and "Última atualização" in HTML
