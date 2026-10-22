from pathlib import Path


HTML = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "index.html"
).read_text(encoding="utf-8")


def test_new_company_has_central_malha_balloon():
    assert 'class="malha-hero-dropzone"' in HTML
    assert "Jogue a malha fiscal aqui" in HTML
    assert "Arraste o PDF para este balão" in HTML
    assert "setMalhaStageMode(false)" in HTML


def test_whole_balloon_opens_file_picker():
    assert "dropzone.addEventListener(" in HTML
    assert "openMalhaFilePicker();" in HTML
    assert "fileInput.addEventListener(" in HTML


def test_file_selection_processes_malha_automatically():
    assert "async function processMalhaFile(file,confirmIdentityMismatch=false)" in HTML
    assert "processMalhaFile(event.target.files?.[0])" in HTML
    assert "formData.append('file',file)" in HTML


def test_summary_replaces_balloon_after_upload():
    assert "setMalhaStageMode(true)" in HTML
    assert "#malhaStageContent.has-malha #workspaceMalhaSection" in HTML
    assert 'id="includeAnotherMalha"' in HTML
