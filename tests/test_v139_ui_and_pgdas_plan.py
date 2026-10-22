from datetime import date
from pathlib import Path

from readers.malha_reader import read_malha_pdf
from services.pgdas_planner import calculate_required_pgdas


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
BATCH = (ROOT / "INICIAR_CHECKFISCAL_WINDOWS.bat").read_text(
    encoding="utf-8"
)


def test_company_form_was_rewritten():
    assert 'id="newCompanyTradeName"' not in HTML
    assert 'id="newCompanyNotes"' not in HTML
    assert HTML.index('id="newCompanyCnpj"') < HTML.index(
        'id="newCompanyLegalName"'
    )
    assert "company-form-success-v139" in HTML
    assert "VERSÃO 1.41" in HTML


def test_workspace_has_no_duplicate_company_title():
    assert '<span id="workspaceCompanyName" hidden></span>' in HTML
    assert '<h1 id="workspaceCompanyName">' not in HTML
    assert "Painel fiscal da empresa</h1>" not in HTML
    assert 'id="contextCnpj"' in HTML
    assert 'id="contextLegalName"' in HTML


def test_back_to_portfolio_is_only_at_bottom():
    assert HTML.count('id="backToPortfolio"') == 1
    assert HTML.index('id="workflowStageHost"') < HTML.index(
        'id="backToPortfolio"'
    )


def test_redundant_blocks_are_removed_from_visual_flow():
    assert "#malhaSummaryCompany," in HTML
    assert "#reflectionCoverage," in HTML
    assert ".redundant-panel-v139" in HTML
    assert ".legacy-pgdas-plan-v139" in HTML


def test_analysis_dark_fix_is_final():
    assert "#analysisStageContent .competence-accordion>summary" in HTML
    assert "background:#0d141f!important" in HTML


def test_browser_cache_is_disabled():
    assert "no-store, no-cache, must-revalidate" in APP


def test_launcher_uses_unique_port():
    assert "127.0.0.1:8141" in BATCH
    assert "--port 8141" in BATCH


def test_aconchego_plan_is_complete_upfront():
    malha = read_malha_pdf(
        Path("/mnt/data/malha fiscal aconchego(3).pdf")
    )
    plan = calculate_required_pgdas(
        malha,
        as_of_date=date(2026, 8, 7),
    )
    assert [
        item["requested_competence"]
        for item in plan["required_pgdas"]
    ] == [
        "06/2022",
        "06/2023",
        "11/2025",
        "06/2026",
    ]
    assert plan["planner"]["strategy"] == "UPFRONT_COMPLETE_PLAN"
