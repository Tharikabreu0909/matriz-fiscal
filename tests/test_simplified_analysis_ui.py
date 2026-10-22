from pathlib import Path
import hashlib


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def sha256(relative_path):
    return hashlib.sha256(
        (ROOT / relative_path).read_bytes()
    ).hexdigest()


def test_accounting_study_is_not_in_the_visible_flow():
    assert "Estudos pendentes" not in HTML
    assert "Conclusão do estudo contábil" not in HTML
    assert "Salvar conclusão do estudo" not in HTML
    assert "/api/conclude-accounting-study" not in HTML


def test_calculation_screen_is_compact_and_details_are_collapsed():
    assert 'class="tax-config compact-tax-config"' in HTML
    assert 'class="compact-summary-grid"' in HTML
    assert 'id="technicalCalculationDetails"' in HTML
    assert "Ver detalhes" in HTML
    assert "Calcular estimativa completa" in HTML


def test_tax_calculator_files_were_not_changed():
    assert sha256("services/tax_engine.py") == "b4eaaf54b6312edd37cf488121e003783842271e89232f0bfdbc8722acda31ac"
    assert sha256("services/legal_charges.py") == "d6e6a17ed4810bc379a2248e4334c33d114e3896d5fdc5233ebbba14ce2a1881"
    assert sha256("services/reflection_coverage.py") == "0b440b854400d5d99769e45f34f36ac6ae247ef21f904312d1728f2a1f2bd0a8"
