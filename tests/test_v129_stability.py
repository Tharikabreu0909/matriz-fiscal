from pathlib import Path


def html_text() -> str:
    static = Path(__file__).resolve().parents[1] / "static"
    return (
        (static / "index.html").read_text(encoding="utf-8")
        + (static / "app.css").read_text(encoding="utf-8")
    )


def test_analysis_has_only_one_visible_competence_list():
    html = html_text()
    assert (
        "#analysisSummarySection #analysisCompetenceList"
        "{display:none!important}"
    ) in html
    assert "Competências analisadas" in html
    assert (
        "Tipo 01 e Tipo 17 aparecem verticalmente"
        in html
    )


def test_malha_stage_is_forced_to_full_width():
    html = html_text()
    assert "#malhaStageContent," in html
    assert "#workList," in html
    assert "max-width:none!important" in html


def test_calculation_has_local_visible_feedback():
    html = html_text()
    assert 'id="calculationMessage"' in html
    assert "function setCalculationMessage" in html
    assert (
        "Estimativa completa: imposto, reflexos, multa e juros calculados."
        in html
    )
    assert (
        "currentReflectionCoverage?.closed_months_complete===true"
        in html
    )
