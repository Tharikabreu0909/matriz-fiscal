from app import (
    build_effective_confirmations,
    calculate_initial_plan_status,
)


def test_effective_confirmations_use_automatic_analysis():
    analysis_result = {
        "analyses": [
            {
                "competence": "04/2025",
                "status": "AUTO_ANALYZED",
                "recommendation": {
                    "pgdas_increment_cents": 100,
                },
            },
            {
                "competence": "05/2025",
                "status": "REVIEW_REQUIRED",
                "recommendation": {
                    "pgdas_increment_cents": 200,
                },
            },
        ]
    }
    stored = [{
        "competence": "05/2025",
        "decision": "CONFIRMED",
        "analysis": {
            "competence": "05/2025",
            "recommendation": {
                "pgdas_increment_cents": 150,
            },
        },
    }]

    effective = build_effective_confirmations(
        analysis_result,
        stored,
    )

    assert len(effective) == 2
    assert effective[0]["decision"] == "AUTO_APPROVED"
    assert effective[1]["decision"] == "CONFIRMED"



def test_initial_plan_requires_own_competence_even_if_later_history_exists():
    process = {
        "pgdas_plan": {
            "required_pgdas": [
                {
                    "requested_competence": "11/2025",
                    "request_kind": "ANALYSIS",
                },
                {
                    "requested_competence": "06/2026",
                    "request_kind": "REFLECTION",
                },
            ]
        }
    }
    accepted = [{
        "assessment": {"period": "06/2026"},
    }]

    status = calculate_initial_plan_status(
        process,
        accepted,
    )

    assert status["analysis_requests_complete"] is False
    assert status["missing_analysis_competences"] == [
        "11/2025"
    ]
    assert status["reflection_requests_complete"] is True
