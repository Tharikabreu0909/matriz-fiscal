from pathlib import Path

import database


def test_accounting_study_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "study.db",
    )
    database.init_db()

    with database.connect() as connection:
        now = database.utc_now()
        connection.execute(
            """
            INSERT INTO processes (
                created_at,
                updated_at,
                company_name,
                company_identifier,
                company_cnpj,
                malha_file_name,
                malha_json,
                pgdas_plan_json,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                "Empresa",
                "CFDF",
                "10689433000150",
                "malha.pdf",
                "{}",
                "{}",
                "TEST",
            ),
        )
        process_id = connection.execute(
            "SELECT id FROM processes"
        ).fetchone()["id"]

    database.save_accounting_study_conclusion(
        process_id,
        "11/2025",
        2_566_600,
        2_566_600,
        "EXTEMPORANEOUS_OTHER_COMPETENCE",
        "Nota de outubro.",
    )

    rows = database.list_accounting_study_conclusions(
        process_id
    )

    assert len(rows) == 1
    assert rows[0]["validated_pgdas_revenue_cents"] == 2_566_600
    assert rows[0]["validated_sped_lfe_revenue_cents"] == 2_566_600



def test_tax_profile_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "profile.db",
    )
    database.init_db()

    with database.connect() as connection:
        now = database.utc_now()
        connection.execute(
            """
            INSERT INTO processes (
                created_at,
                updated_at,
                company_name,
                company_identifier,
                company_cnpj,
                malha_file_name,
                malha_json,
                pgdas_plan_json,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                "Empresa",
                "CFDF",
                "10689433000150",
                "malha.pdf",
                "{}",
                "{}",
                "TEST",
            ),
        )
        process_id = connection.execute(
            "SELECT id FROM processes"
        ).fetchone()["id"]

    profile = {
        "base_distribution": [
            {
                "category": "COMMERCE_NORMAL",
                "basis_points": 10000,
            }
        ]
    }
    database.save_tax_profile(
        process_id,
        "CONSERVATIVE_FISCAL_EXPOSURE",
        profile,
    )

    saved = database.list_tax_profiles(process_id)

    assert saved[
        "CONSERVATIVE_FISCAL_EXPOSURE"
    ] == profile
