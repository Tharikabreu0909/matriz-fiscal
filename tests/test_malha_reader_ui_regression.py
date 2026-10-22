from pathlib import Path

HTML = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "index.html"
).read_text(encoding="utf-8")


def test_removed_pgdas_cta_is_null_safe_after_malha_reader():
    assert "const cta=document.getElementById('pgdasCta');" in HTML
    assert "if(cta)cta.style.display='flex';" in HTML
    assert "cta.style.display='flex';" not in HTML.replace(
        "if(cta)cta.style.display='flex';", ""
    )


def test_reflection_coverage_does_not_create_new_document_requests():
    start = HTML.index("function renderReflectionCoverage(coverage){")
    end = HTML.index("function brlPgdas(cents){", start)
    block = HTML[start:end]

    assert "const requests=document.getElementById('requests');" in block
    assert "if(requests){" in block
    assert "insertAdjacentHTML" not in block
    assert "supplementalCardHtml" not in block


def test_central_balloon_remains_in_place():
    assert 'class="malha-hero-dropzone"' in HTML
    assert "Jogue a malha fiscal aqui" in HTML
    assert "async function processMalhaFile(file,confirmIdentityMismatch=false)" in HTML
