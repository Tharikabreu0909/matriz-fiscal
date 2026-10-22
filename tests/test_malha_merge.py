from services.malha_merge import merge_malhas


def malha(competence, type_code, divergence):
    row = {
        "id": 1,
        "type_code": type_code,
        "reference": f"01/{competence}",
        "competence": competence,
        "informed_field": "PGDAS_INFORMED",
        "informed_cents": 100,
        "considered_cents": 100 + divergence,
        "divergence_cents": divergence,
        "duplicate": False,
        "duplicate_of": None,
    }
    return {
        "reader": {},
        "source_document": {"file_name": f"{competence}.pdf", "sha256": competence},
        "contributor": {"legal_name": "Empresa", "cfdf": "123"},
        "raw_rows": [row],
        "work_months": [],
        "explanatory_notes": "",
    }


def test_merge_keeps_one_process_and_adds_competences():
    result = merge_malhas(
        malha("01/2025", "17", 1000),
        malha("03/2025", "01", 2000),
    )
    assert [item["competence"] for item in result["work_months"]] == ["01/2025", "03/2025"]
    assert result["summary"]["raw_row_count"] == 2
    assert len(result["source_documents"]) == 2


def test_merge_marks_repeated_notice_as_duplicate():
    first = malha("01/2025", "17", 1000)
    result = merge_malhas(first, first)
    assert result["summary"]["raw_row_count"] == 2
    assert result["summary"]["duplicate_row_count"] == 1
