from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_requirements_do_not_install_uvicorn_standard_extra():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "uvicorn==0.35.0" in requirements
    assert "uvicorn[standard]" not in requirements
    assert "pyyaml" not in requirements.lower()


def test_windows_launcher_selects_supported_python_and_unique_port():
    launcher = (ROOT / "INICIAR_CHECKFISCAL_WINDOWS.bat").read_text(encoding="utf-8")
    assert "py -3.13" in launcher
    assert "py -3.12" in launcher
    assert "py -3.11" in launcher
    assert "8145" in launcher
    assert "Add Python to PATH" in launcher
    assert ".checkfiscal-deps-1.45" in launcher


def test_current_version_matches_api_and_ui():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.45.0"' in app
    assert "VERSÃO 1.45" in html
