from pathlib import Path
from readers.malha_reader import read_malha_pdf
from readers.pgdas_reader import read_pgdas_pdf
from services.analysis_engine import analyze_process
from services.client_report import build_report_model, render_client_report

MALHA = Path("/mnt/data/MALHA FISCAL RF(1).pdf")
PGDAS = Path("/mnt/data/PGDASD-DECLARACAO-39588299202511004.pdf")


def test_r_fiscal_pdf_reads_continuation_and_type17_on_page_two():
    if not MALHA.exists() or not PGDAS.exists():
        return
    malha = read_malha_pdf(MALHA)
    assert malha["summary"]["raw_row_count"] == 23
    assert malha["summary"]["work_month_count"] == 19
    assert {row["competence"] for row in malha["raw_rows"] if row["page"] == 2} == {
        "12/2025", "01/2026", "06/2026", "05/2025"
    }
    month = next(x for x in malha["work_months"] if x["competence"] == "12/2025")
    notice = next(x for x in month["notices"] if x["type_code"] == "17")
    assert notice["divergence_cents"] == 25578061
    pgdas = read_pgdas_pdf(PGDAS)
    result = analyze_process(malha, [pgdas])
    by_comp = {x["competence"]: x for x in result["analyses"]}
    assert by_comp["05/2025"]["recommendation"]["simulation_pgdas_increment_cents"] == 3348843
    for competence in ("12/2025", "01/2026", "06/2026"):
        assert by_comp[competence]["status"] == "AWAITING_PGDAS"
    report = build_report_model(
        {"malha": malha, "company_name": "RAFAEL M.S. IMPORTADOS"},
        result, [], {"summary": {}}, {"summary": {}},
    )
    assert len(report["competence_rows"]) == 19
    html = render_client_report(report)
    assert "12/2025" in html and "01/2026" in html and "06/2026" in html
    assert "R$ 255.780,61" in html
