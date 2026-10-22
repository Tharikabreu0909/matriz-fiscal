from pathlib import Path


def test_removed_legacy_requests_is_rendered_safely():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "const legacyRequests=document.getElementById('requests');" in html
    assert "if(legacyRequests){" in html
    assert "document.getElementById('requests').innerHTML" not in html


def test_pgdas_grid_has_explicit_guard():
    html = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "const pgdasGrid=document.getElementById('pgdasUploadGrid');" in html
    assert "if(!pgdasGrid){" in html
