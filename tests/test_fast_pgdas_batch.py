from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_redundant_uploaded_file_list_was_removed():
    assert 'id="bulkUploadResults"' not in HTML
    assert 'id="bulkUploadFeedback"' in HTML
    assert "bulk-result accepted" not in HTML


def test_frontend_sends_all_files_in_one_request():
    assert "pdfs.forEach(file=>form.append('files',file))" in HTML
    assert "for(const [index,file] of pdfs.entries())" not in HTML
    assert "Lendo ${pdfs.length} arquivo(s)" in HTML


def test_backend_parses_files_in_parallel_once():
    assert "asyncio.gather(" in APP
    assert "asyncio.to_thread(" in APP
    assert "_read_pgdas_content" in APP

    auto_block = APP.split(
        '@app.post("/api/upload-pgdas-auto")',
        1,
    )[1].split(
        '@app.get("/api/process/{process_id}")',
        1,
    )[0]

    assert "await upload_pgdas(" not in auto_block
    assert 'save_pgdas_document(' in auto_block


def test_progress_cards_remain_the_only_success_list():
    assert 'id="pgdasUploadGrid"' in HTML
    assert "setPgdasCardState(" in HTML
    assert "Concluído" in HTML
