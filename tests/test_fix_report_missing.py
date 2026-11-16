"""Relatório: competência sem cálculo não pode parecer zero legítimo (sintético)."""
import hashlib

from services.client_report import build_report_model, render_client_report
from tests.test_client_report import fixtures


def _model(missing_months=None):
    process, analysis, tax, charges = fixtures()
    if missing_months is not None:
        tax["missing_months"] = missing_months
    return build_report_model(process, analysis, [], tax, charges)


def _fix_clock(model):
    model["generated_at"] = "01/01/2026 às 00:00"
    return model


# sha256 do HTML gerado pelo código ANTES da correção (modelo sintético, relógio fixo)
HTML_SHA256_BEFORE_FIX = "abef5900a8fe4a9792d96558bbc4db2ad0eb311e8a18ab5adb1318ed29448c37"


def test_html_without_missing_months_is_byte_identical():
    for model in (_model(), _model([])):
        html = render_client_report(_fix_clock(model))
        assert hashlib.sha256(html.encode()).hexdigest() == HTML_SHA256_BEFORE_FIX
        assert "Cálculo pendente de documentação" not in html


def test_missing_competence_shows_reason_instead_of_zero():
    model = _fix_clock(_model([{
        "competence": "04/2025",
        "missing_competences": ["06/2024", "07/2024", "08/2024", "12/2024"],
    }]))
    html = render_client_report(model)
    assert "Cálculo pendente de documentação" in html
    assert "faltam PGDAS que cubram 06/2024 a 08/2024, 12/2024" in html
    assert "R$ 1.240,00" not in html.split("Pontos de atenção")[1].split("</table>")[0]
    assert html.count("Cálculo pendente de documentação") == 1


def test_missing_reflection_month_outside_malha_is_not_flagged():
    model = _fix_clock(_model([{
        "competence": "09/2025", "missing_competences": ["09/2024"],
    }]))
    assert "Cálculo pendente de documentação" not in render_client_report(model)
