from services.analysis_engine import analyze_process


def malha_fixture():
    return {
        "work_months": [
            {
                "competence": "06/2025",
                "types": ["01"],
                "notices": [
                    {
                        "type_code": "01",
                        "informed_cents": 1921000,
                        "considered_cents": 3777614,
                        "divergence_cents": 1856614,
                    }
                ],
            },
            {
                "competence": "07/2025",
                "types": ["01", "17"],
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


def pgdas_fixture(declared=4762500):
    return {
        "source_document": {
            "file_name": "pgdas-072025.pdf",
        },
        "assessment": {
            "period": "07/2025",
            "revenue_summary": {
                "rpa": {"total_cents": declared},
            },
            "previous_revenues": [],
        },
    }


def test_sped_only_month():
    result = analyze_process(
        malha_fixture(),
        [pgdas_fixture()],
    )
    june = result["analyses"][0]

    assert june["status"] == "AUTO_ANALYZED"
    assert june["requires_review"] is False
    assert june["recommendation"]["sped_increment_cents"] == 1856614
    assert june["recommendation"]["pgdas_increment_cents"] == 0


def test_both_types_matching_sources():
    result = analyze_process(
        malha_fixture(),
        [pgdas_fixture()],
    )
    july = result["analyses"][1]

    assert july["status"] == "AUTO_ANALYZED"
    assert july["requires_review"] is False
    assert july["source_consistency"] == "MATCH"
    assert july["recommendation"]["sped_increment_cents"] == 142704
    assert july["recommendation"]["pgdas_increment_cents"] == 142704
    assert july["recommendation"]["calculate_direct_tax"] is True
    assert july["recommendation"]["calculate_rbt12_reflections"] is True


def test_pgdas_differs_from_malha():
    result = analyze_process(
        malha_fixture(),
        [pgdas_fixture(declared=4800000)],
    )
    july = result["analyses"][1]

    assert july["status"] == "REVIEW_REQUIRED"
    assert july["source_consistency"] == "DIFFERENT_FROM_MALHA"
    assert july["recommendation"]["pgdas_increment_cents"] == 105204


def test_missing_pgdas():
    result = analyze_process(
        malha_fixture(),
        [],
    )
    july = result["analyses"][1]

    assert july["status"] == "AWAITING_PGDAS"



def test_type_01_and_17_different_values_are_segregated():
    malha = {
        "work_months": [{
            "competence": "04/2025",
            "types": ["01", "17"],
            "notices": [
                {
                    "type_code": "01",
                    "informed_cents": 3_000_000,
                    "considered_cents": 5_000_000,
                    "divergence_cents": 2_000_000,
                },
                {
                    "type_code": "17",
                    "informed_cents": 3_500_000,
                    "considered_cents": 5_500_000,
                    "divergence_cents": 2_000_000,
                },
            ],
        }],
    }
    pgdas = {
        "source_document": {"file_name": "pgdas.pdf"},
        "assessment": {
            "period": "04/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 3_500_000},
            },
            "previous_revenues": [],
        },
    }

    item = analyze_process(malha, [pgdas])["analyses"][0]
    segregation = item["segregation"]

    assert segregation["cross_type_comparison"] == (
        "DIFFERENT_CONSIDERED_VALUES"
    )
    assert segregation["type_01"][
        "minimum_gap_cents"
    ] == 2_000_000
    assert segregation["type_01"][
        "recommended_target_cents"
    ] is None
    assert segregation["type_17"][
        "simulation_increment_cents"
    ] == 2_000_000
    assert segregation["type_17"][
        "simulation_target_cents"
    ] == 5_500_000
    assert segregation["type_17"][
        "recommended_target_cents"
    ] is None
    assert segregation["consolidated"][
        "tax_base_increment_cents"
    ] == 2_000_000
    assert segregation["consolidated"][
        "combined_divergence_cents"
    ] is None
    assert segregation["consolidated"][
        "calculation_rule"
    ] == (
        "USE_TYPE_17_FOR_EXPOSURE_"
        "DO_NOT_INFER_FINAL_SPED_TARGET"
    )
    assert segregation["consolidated"][
        "tax_source"
    ] == "TYPE_17_ONLY"


def test_type_01_does_not_create_tax_when_pgdas_needs_no_change():
    malha = {
        "work_months": [{
            "competence": "04/2025",
            "types": ["01", "17"],
            "notices": [
                {
                    "type_code": "01",
                    "informed_cents": 3_000_000,
                    "considered_cents": 5_000_000,
                    "divergence_cents": 2_000_000,
                },
                {
                    "type_code": "17",
                    "informed_cents": 5_500_000,
                    "considered_cents": 5_500_000,
                    "divergence_cents": 0,
                },
            ],
        }],
    }
    pgdas = {
        "source_document": {"file_name": "pgdas.pdf"},
        "assessment": {
            "period": "04/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 5_500_000},
            },
            "previous_revenues": [],
        },
    }

    item = analyze_process(malha, [pgdas])["analyses"][0]

    assert item["segregation"]["type_01"][
        "recommended_increment_cents"
    ] == 2_000_000
    assert item["segregation"]["type_17"][
        "recommended_increment_cents"
    ] == 0
    assert item["segregation"]["consolidated"][
        "tax_base_increment_cents"
    ] == 0
    assert item["recommendation"]["calculate_direct_tax"] is False
    assert item["recommendation"][
        "calculate_rbt12_reflections"
    ] is False



def test_only_conflicts_require_review():
    normal = analyze_process(
        malha_fixture(),
        [pgdas_fixture()],
    )
    conflict = analyze_process(
        malha_fixture(),
        [pgdas_fixture(declared=4_800_000)],
    )

    assert normal["summary"]["review_required_count"] == 0
    assert normal["summary"]["auto_analyzed_count"] == 2
    assert all(
        item["requires_review"] is False
        for item in normal["analyses"]
    )

    july = conflict["analyses"][1]
    assert july["status"] == "REVIEW_REQUIRED"
    assert july["requires_review"] is True
    assert july["automation"]["mode"] == "EXCEPTION_REVIEW"



def test_real_november_case_separates_exposure_from_regularization():
    malha = {
        "work_months": [{
            "competence": "11/2025",
            "types": ["01", "17"],
            "notices": [
                {
                    "type_code": "01",
                    "informed_cents": 0,
                    "considered_cents": 1_664_701,
                    "divergence_cents": 1_664_701,
                },
                {
                    "type_code": "17",
                    "informed_cents": 2_566_600,
                    "considered_cents": 5_503_590,
                    "divergence_cents": 2_936_990,
                },
            ],
        }],
    }
    pgdas = {
        "source_document": {
            "file_name": "pgdas-112025.pdf",
        },
        "assessment": {
            "period": "11/2025",
            "revenue_summary": {
                "rpa": {"total_cents": 2_566_600},
            },
            "previous_revenues": [],
        },
    }

    item = analyze_process(malha, [pgdas])["analyses"][0]
    type_01 = item["segregation"]["type_01"]
    type_17 = item["segregation"]["type_17"]
    consolidated = item["segregation"]["consolidated"]
    study = item["segregation"]["accounting_study"]

    assert type_01["minimum_detected_cents"] == 1_664_701
    assert type_01["recommended_target_cents"] is None
    assert type_01["interpretation"] == (
        "MINIMUM_DIVERGENCE_NOT_FINAL_BOOK_VALUE"
    )

    assert type_17["simulation_target_cents"] == 5_503_590
    assert type_17["simulation_increment_cents"] == 2_936_990
    assert type_17["regularization_target_cents"] is None

    assert consolidated["simulation_revenue_cents"] == 5_503_590
    assert consolidated[
        "simulation_tax_base_increment_cents"
    ] == 2_936_990
    assert consolidated["sped_lfe_target_cents"] is None
    assert consolidated["pgdas_target_cents"] is None
    assert consolidated["regularization_status"] == (
        "PENDING_ACCOUNTING_STUDY"
    )

    assert study["required"] is True
    assert study["blocks_exposure_simulation"] is False
    assert study[
        "blocks_final_regularization_instruction"
    ] is True

    action_names = {
        action["action"]
        for action in item["actions"]
    }
    assert "RECONSTRUCT_SPED_LFE" in action_names
    assert "SIMULATE_PGDAS_EXPOSURE" in action_names
    assert "RECTIFY_SPED_LFE" not in action_names
    assert "RECTIFY_PGDAS" not in action_names
