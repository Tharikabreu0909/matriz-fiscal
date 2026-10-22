from pathlib import Path


HTML = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "index.html"
).read_text(encoding="utf-8")


def test_calculation_has_only_one_main_action():
    assert "Calcular estimativa completa" in HTML
    assert 'id="calculateChargesButton"' not in HTML
    assert "Calcular multa e juros" not in HTML


def test_update_date_is_selected_before_calculation():
    assert 'id="chargesUpdateDate"' in HTML
    assert "Informe a data para atualização da multa e dos juros." in HTML


def test_tax_handler_automatically_requests_legal_charges():
    assert "async function requestAutomaticLegalCharges(updateDate)" in HTML
    assert "const chargesPayload=await requestAutomaticLegalCharges(" in HTML
    assert "renderLegalCharges(chargesPayload.legal_charges)" in HTML
    assert "Atualizando multa e juros..." in HTML


def test_complete_result_unlocks_report():
    assert "setAnalysisTabEnabled('report',true)" in HTML
    assert (
        "Estimativa completa: imposto, reflexos, multa e juros calculados."
        in HTML
    )
