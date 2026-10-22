from services.cross_engine import (
    cross_malha_with_pgdas,
    validate_pgdas_identity,
)


def malha_fixture():
    return {
        "contributor": {
            "cfdf": "08.055.883/001-11",
            "legal_name": "ACONCHEGO",
        },
        "work_months": [
            {
                "competence": "06/2025",
                "types": ["01"],
                "raw_row_count": 2,
                "duplicate_count": 1,
                "notices": [
                    {
                        "type_code": "01",
                        "informed_cents": 1921000,
                        "considered_cents": 3777614,
                        "divergence_cents": 1856614,
                        "duplicate": False,
                    },
                    {
                        "type_code": "01",
                        "informed_cents": 1921000,
                        "considered_cents": 3777614,
                        "divergence_cents": 1856614,
                        "duplicate": True,
                    },
                ],
            },
            {
                "competence": "07/2025",
                "types": ["01", "17"],
                "raw_row_count": 2,
                "duplicate_count": 0,
                "notices": [
                    {
                        "type_code": "01",
                        "informed_cents": 4762500,
                        "considered_cents": 4905204,
                        "divergence_cents": 142704,
                    },
                    {
                        "type_code": "17",
                        "informed_cents": 4762500,
                        "considered_cents": 4905204,
                        "divergence_cents": 142704,
                    },
                ],
            },
        ],
    }


def matching_pgdas():
    return {
        "taxpayer": {
            "basic_cnpj": "08.055.883",
            "full_cnpjs_found": ["08.055.883/0001-11"],
        },
        "source_document": {
            "file_name": "pgdas-072025.pdf",
        },
        "assessment": {
            "period": "07/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 4762500},
            },
            "previous_revenues": [],
        },
    }


def test_identity_match():
    identity = validate_pgdas_identity(
        "08.055.883/0001-11",
        matching_pgdas(),
    )
    assert identity["match"] is True


def test_identity_mismatch():
    pgdas = matching_pgdas()
    pgdas["taxpayer"]["basic_cnpj"] = "09.462.429"
    pgdas["taxpayer"]["full_cnpjs_found"] = [
        "09.462.429/0001-75"
    ]

    identity = validate_pgdas_identity(
        "08.055.883/0001-11",
        pgdas,
    )
    assert identity["match"] is False


def test_cross_actions():
    result = cross_malha_with_pgdas(
        malha_fixture(),
        [matching_pgdas()],
    )

    june = result["diagnostics"][0]
    july = result["diagnostics"][1]

    assert june["type_results"]["01"]["correction_cents"] == 1856614
    assert june["status"] == "ACTION_REQUIRED"

    assert july["type_results"]["01"]["correction_cents"] == 142704
    assert july["type_results"]["17"]["correction_cents"] == 142704

    action_names = {
        action["action"]
        for action in july["actions"]
    }
    assert "RECTIFY_SPED_LFE" in action_names
    assert "RECTIFY_PGDAS" in action_names
    assert "CALCULATE_DIRECT_TAX" in action_names
    assert "CALCULATE_RBT12_REFLECTIONS" in action_names
