from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import json
import os
import sqlite3


from services.runtime_paths import DB_PATH
from services.security import validate_cnpj


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _column_names(
    connection: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _column_names(connection, table):
        connection.execute(
            f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}'
        )


def _run_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )

    _ensure_column(
        connection,
        "processes",
        "company_cnpj",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        connection,
        "processes",
        "company_id",
        "INTEGER",
    )
    _ensure_column(
        connection,
        "tax_calculations",
        "scenario",
        "TEXT NOT NULL DEFAULT 'CONSERVATIVE_FISCAL_EXPOSURE'",
    )
    _ensure_column(
        connection,
        "legal_charge_calculations",
        "scenario",
        "TEXT NOT NULL DEFAULT 'CONSERVATIVE_FISCAL_EXPOSURE'",
    )

    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, applied_at)
        VALUES (1, ?)
        """,
        (utc_now(),),
    )
    connection.execute("PRAGMA user_version = 2")


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                cnpj TEXT NOT NULL UNIQUE,
                legal_name TEXT NOT NULL,
                trade_name TEXT NOT NULL,
                state_registration TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                default_annex TEXT NOT NULL,
                notes TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                company_name TEXT NOT NULL,
                company_identifier TEXT NOT NULL,
                company_cnpj TEXT NOT NULL,
                malha_file_name TEXT NOT NULL,
                malha_json TEXT NOT NULL,
                pgdas_plan_json TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS pgdas_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                requested_competence TEXT NOT NULL,
                extracted_competence TEXT NOT NULL,
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                identity_status TEXT NOT NULL,
                competence_status TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                pgdas_json TEXT NOT NULL,
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );


            CREATE TABLE IF NOT EXISTS analysis_confirmations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                competence TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                decision TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                UNIQUE(process_id, competence),
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );


            CREATE TABLE IF NOT EXISTS accounting_study_conclusions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                competence TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                validated_pgdas_revenue_cents INTEGER,
                validated_sped_lfe_revenue_cents INTEGER,
                reason_code TEXT NOT NULL,
                notes TEXT NOT NULL,
                UNIQUE(process_id, competence),
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );

            CREATE TABLE IF NOT EXISTS tax_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                scenario TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                UNIQUE(process_id, scenario),
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );

            CREATE TABLE IF NOT EXISTS tax_calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                annex TEXT NOT NULL,
                profile TEXT NOT NULL,
                scenario TEXT NOT NULL,
                calculation_json TEXT NOT NULL,
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );


            CREATE TABLE IF NOT EXISTS legal_charge_calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                update_date TEXT NOT NULL,
                scenario TEXT NOT NULL,
                calculation_json TEXT NOT NULL,
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );


            CREATE TABLE IF NOT EXISTS client_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                update_date TEXT NOT NULL,
                report_json TEXT NOT NULL,
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );

            CREATE TABLE IF NOT EXISTS process_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                company_id INTEGER,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(process_id) REFERENCES processes(id),
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE INDEX IF NOT EXISTS idx_processes_company
                ON processes(company_id, id);
            CREATE INDEX IF NOT EXISTS idx_process_events_process
                ON process_events(process_id, id);

            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                competence TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                diagnostic_json TEXT NOT NULL,
                UNIQUE(process_id, competence),
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );

            CREATE TABLE IF NOT EXISTS stored_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                process_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                competence TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(process_id, kind, sha256),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                FOREIGN KEY(process_id) REFERENCES processes(id)
            );

            CREATE INDEX IF NOT EXISTS idx_stored_documents_process
                ON stored_documents(process_id, id);
            """
        )
        _run_migrations(connection)


def normalize_cnpj(value: str) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def create_company(
    cnpj: str,
    legal_name: str,
    trade_name: str = "",
    state_registration: str = "",
    city: str = "",
    state: str = "",
    default_annex: str = "I",
    notes: str = "",
) -> int:
    normalized = validate_cnpj(cnpj)
    legal_name = str(legal_name or "").strip()
    if not legal_name:
        raise ValueError("Informe a razão social.")
    if default_annex not in {"I", "II", "III", "IV", "V"}:
        raise ValueError("Selecione um anexo padrão entre I e V.")
    now = utc_now()
    try:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO companies (
                    created_at, updated_at, cnpj, legal_name,
                    trade_name, state_registration, city, state,
                    default_annex, notes, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now, now, normalized, legal_name,
                    str(trade_name or "").strip(),
                    str(state_registration or "").strip(),
                    str(city or "").strip(),
                    str(state or "").strip().upper(),
                    default_annex,
                    str(notes or "").strip(),
                    "HEALTHY",
                ),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        raise ValueError("Já existe uma empresa cadastrada com este CNPJ.") from error


def update_company(
    company_id: int,
    **fields: Any,
) -> None:
    allowed = {
        "legal_name", "trade_name", "state_registration",
        "city", "state", "default_annex", "notes", "status",
    }
    values = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not values:
        return
    if "default_annex" in values and values["default_annex"] not in {"I", "II", "III", "IV", "V"}:
        raise ValueError("Selecione um anexo padrão entre I e V.")
    if "state" in values:
        values["state"] = str(values["state"]).upper()
    values["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in values)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE companies SET {assignments} WHERE id = ?",
            (*values.values(), company_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Empresa {company_id} não encontrada.")


def get_company(company_id: int) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Empresa {company_id} não encontrada.")
    return dict(row)


def delete_company(company_id: int) -> None:
    """Exclui a empresa e todos os dados locais ligados a ela."""
    child_tables = (
        "pgdas_documents",
        "analysis_confirmations",
        "accounting_study_conclusions",
        "tax_profiles",
        "tax_calculations",
        "legal_charge_calculations",
        "client_reports",
        "diagnostics",
        "stored_documents",
    )

    with connect() as connection:
        company = connection.execute(
            "SELECT id FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        if company is None:
            raise KeyError(f"Empresa {company_id} não encontrada.")

        process_rows = connection.execute(
            "SELECT id FROM processes WHERE company_id = ?",
            (company_id,),
        ).fetchall()
        process_ids = [int(row["id"]) for row in process_rows]

        for process_id in process_ids:
            for table in child_tables:
                connection.execute(
                    f"DELETE FROM {table} WHERE process_id = ?",
                    (process_id,),
                )
            connection.execute(
                "DELETE FROM process_events WHERE process_id = ?",
                (process_id,),
            )

        connection.execute(
            "DELETE FROM process_events WHERE company_id = ?",
            (company_id,),
        )
        connection.execute(
            "DELETE FROM processes WHERE company_id = ?",
            (company_id,),
        )
        connection.execute(
            "DELETE FROM companies WHERE id = ?",
            (company_id,),
        )


def get_company_active_process(company_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM processes
            WHERE company_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (company_id,),
        ).fetchone()
    return get_process(int(row["id"])) if row else None


def update_process_malha(
    process_id: int,
    malha: dict[str, Any],
    pgdas_plan: dict[str, Any],
    company_name: str,
    company_identifier: str,
    malha_file_name: str,
) -> None:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE processes
            SET updated_at = ?, company_name = ?, company_identifier = ?,
                malha_file_name = ?, malha_json = ?, pgdas_plan_json = ?,
                status = ?
            WHERE id = ?
            """,
            (
                utc_now(), company_name, company_identifier,
                malha_file_name,
                json.dumps(malha, ensure_ascii=False),
                json.dumps(pgdas_plan, ensure_ascii=False),
                "AWAITING_PGDAS", process_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Processo {process_id} não encontrado.")


def invalidate_process_analysis(process_id: int) -> None:
    """Remove resultados derivados quando a malha do processo muda.

    Os PGDAS aceitos são preservados porque podem continuar cobrindo o
    processo atualizado. Diagnósticos, cálculos e relatórios são refeitos.
    """
    tables = (
        "diagnostics",
        "analysis_confirmations",
        "accounting_study_conclusions",
        "tax_profiles",
        "tax_calculations",
        "legal_charge_calculations",
        "client_reports",
    )
    with connect() as connection:
        for table in tables:
            connection.execute(
                f"DELETE FROM {table} WHERE process_id = ?",
                (process_id,),
            )


def accepted_pgdas_periods(process_id: int) -> set[str]:
    return {
        item.get("assessment", {}).get("period", "")
        for item in list_accepted_pgdas(process_id)
        if item.get("assessment", {}).get("period")
    }


def update_process_pgdas_plan(
    process_id: int,
    pgdas_plan: dict[str, Any],
) -> None:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE processes
            SET pgdas_plan_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(pgdas_plan, ensure_ascii=False),
                utc_now(),
                process_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Processo {process_id} não encontrado.")


def append_process_event(
    process_id: int,
    event_type: str,
    title: str,
    details: dict[str, Any] | None = None,
) -> int:
    process = get_process(process_id)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO process_events (
                process_id, company_id, created_at,
                event_type, title, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                process_id, process.get("company_id"), utc_now(),
                event_type, title,
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def list_process_events(process_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT created_at, event_type, title, details_json
            FROM process_events
            WHERE process_id = ?
            ORDER BY id DESC
            """,
            (process_id,),
        ).fetchall()
    return [
        {
            "created_at": row["created_at"],
            "event_type": row["event_type"],
            "title": row["title"],
            "details": json.loads(row["details_json"]),
        }
        for row in rows
    ]


def list_companies() -> list[dict[str, Any]]:
    with connect() as connection:
        companies = connection.execute(
            "SELECT * FROM companies ORDER BY legal_name COLLATE NOCASE"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for company_row in companies:
        company = dict(company_row)
        process = get_company_active_process(company["id"])
        exposure = 0
        process_status = "HEALTHY"
        competence_count = 0
        type_01_count = 0
        type_17_count = 0
        required_pgdas_count = 0
        accepted_pgdas_count = 0
        latest_event_title = "Empresa cadastrada"
        report_available = False
        if process:
            process_status = process["status"]
            charges = latest_legal_charge_calculation(process["id"])
            tax = latest_tax_calculation(process["id"])
            if charges:
                exposure = int(charges.get("summary", {}).get("total_cents", 0) or 0)
            elif tax:
                exposure = int(tax.get("summary", {}).get("estimated_total_cents", 0) or 0)
            work_months = process.get("malha", {}).get("work_months", [])
            competence_count = len(work_months)
            type_01_count = sum("01" in item.get("types", []) for item in work_months)
            type_17_count = sum("17" in item.get("types", []) for item in work_months)
            required_requests = process.get("pgdas_plan", {}).get("required_pgdas", [])
            required_pgdas_count = len(required_requests)
            required_periods = {
                item.get("requested_competence", "")
                for item in required_requests
            }
            accepted_pgdas_count = len(
                accepted_pgdas_periods(process["id"]) & required_periods
            )
            events = list_process_events(process["id"])
            if events:
                latest_event_title = events[0]["title"]
            report_available = latest_client_report(process["id"]) is not None
        result.append({
            **company,
            "active_process_id": process["id"] if process else None,
            "process_status": process_status,
            "exposure_estimated_cents": exposure,
            "last_activity_at": process["updated_at"] if process else company["updated_at"],
            "competence_count": competence_count,
            "type_01_count": type_01_count,
            "type_17_count": type_17_count,
            "required_pgdas_count": required_pgdas_count,
            "accepted_pgdas_count": accepted_pgdas_count,
            "latest_event_title": latest_event_title,
            "report_available": report_available,
        })
    return result


def list_recent_process_events(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT e.created_at, e.event_type, e.title, e.details_json,
                   e.process_id, e.company_id, c.legal_name AS company_name
            FROM process_events e
            LEFT JOIN companies c ON c.id = e.company_id
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [
        {
            "created_at": row["created_at"],
            "event_type": row["event_type"],
            "title": row["title"],
            "details": json.loads(row["details_json"]),
            "process_id": row["process_id"],
            "company_id": row["company_id"],
            "company_name": row["company_name"] or "Empresa não identificada",
        }
        for row in rows
    ]

def create_process(
    malha: dict[str, Any],
    pgdas_plan: dict[str, Any],
    company_cnpj: str,
    company_id: int | None = None,
) -> int:
    now = utc_now()
    contributor = malha.get("contributor", {})

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO processes (
                company_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                now,
                now,
                contributor.get("legal_name", ""),
                contributor.get("cfdf", ""),
                company_cnpj,
                malha.get("source_document", {}).get(
                    "file_name",
                    "malha.pdf",
                ),
                json.dumps(malha, ensure_ascii=False),
                json.dumps(pgdas_plan, ensure_ascii=False),
                "AWAITING_PGDAS",
            ),
        )
        return int(cursor.lastrowid)


def get_process(process_id: int) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM processes WHERE id = ?",
            (process_id,),
        ).fetchone()

    if row is None:
        raise KeyError(f"Processo {process_id} não encontrado.")

    return {
        "id": row["id"],
        "company_id": row["company_id"] if "company_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "company_name": row["company_name"],
        "company_identifier": row["company_identifier"],
        "company_cnpj": row["company_cnpj"],
        "status": row["status"],
        "malha": json.loads(row["malha_json"]),
        "pgdas_plan": json.loads(row["pgdas_plan_json"]),
    }


def save_pgdas_document(
    process_id: int,
    requested_competence: str,
    pgdas: dict[str, Any],
    identity_status: str,
    competence_status: str,
    accepted: bool,
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO pgdas_documents (
                process_id,
                created_at,
                requested_competence,
                extracted_competence,
                file_name,
                sha256,
                identity_status,
                competence_status,
                accepted,
                pgdas_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                process_id,
                utc_now(),
                requested_competence,
                pgdas.get("assessment", {}).get("period", ""),
                pgdas.get("source_document", {}).get(
                    "file_name",
                    "pgdas.pdf",
                ),
                pgdas.get("source_document", {}).get("sha256", ""),
                identity_status,
                competence_status,
                1 if accepted else 0,
                json.dumps(pgdas, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def list_accepted_pgdas(process_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT pgdas_json
            FROM pgdas_documents
            WHERE process_id = ? AND accepted = 1
            ORDER BY id
            """,
            (process_id,),
        ).fetchall()

    return [
        json.loads(row["pgdas_json"])
        for row in rows
    ]


def save_diagnostics(
    process_id: int,
    diagnostics: list[dict[str, Any]],
) -> None:
    now = utc_now()

    with connect() as connection:
        for diagnostic in diagnostics:
            connection.execute(
                """
                INSERT INTO diagnostics (
                    process_id,
                    competence,
                    updated_at,
                    diagnostic_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(process_id, competence)
                DO UPDATE SET
                    updated_at = excluded.updated_at,
                    diagnostic_json = excluded.diagnostic_json
                """,
                (
                    process_id,
                    diagnostic["competence"],
                    now,
                    json.dumps(diagnostic, ensure_ascii=False),
                ),
            )


def update_process_status(
    process_id: int,
    status: str,
) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE processes
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, utc_now(), process_id),
        )


def save_analysis_confirmation(
    process_id: int,
    competence: str,
    decision: str,
    analysis: dict[str, Any],
) -> None:
    now = utc_now()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO analysis_confirmations (
                process_id,
                competence,
                created_at,
                updated_at,
                decision,
                analysis_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_id, competence)
            DO UPDATE SET
                updated_at = excluded.updated_at,
                decision = excluded.decision,
                analysis_json = excluded.analysis_json
            """,
            (
                process_id,
                competence,
                now,
                now,
                decision,
                json.dumps(analysis, ensure_ascii=False),
            ),
        )


def list_analysis_confirmations(
    process_id: int,
) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT competence, decision, analysis_json
            FROM analysis_confirmations
            WHERE process_id = ?
            ORDER BY competence
            """,
            (process_id,),
        ).fetchall()

    return [
        {
            "competence": row["competence"],
            "decision": row["decision"],
            "analysis": json.loads(row["analysis_json"]),
        }
        for row in rows
    ]



def save_accounting_study_conclusion(
    process_id: int,
    competence: str,
    validated_pgdas_revenue_cents: int | None,
    validated_sped_lfe_revenue_cents: int | None,
    reason_code: str,
    notes: str,
    status: str = "VALIDATED",
) -> None:
    now = utc_now()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO accounting_study_conclusions (
                process_id,
                competence,
                created_at,
                updated_at,
                status,
                validated_pgdas_revenue_cents,
                validated_sped_lfe_revenue_cents,
                reason_code,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_id, competence)
            DO UPDATE SET
                updated_at = excluded.updated_at,
                status = excluded.status,
                validated_pgdas_revenue_cents =
                    excluded.validated_pgdas_revenue_cents,
                validated_sped_lfe_revenue_cents =
                    excluded.validated_sped_lfe_revenue_cents,
                reason_code = excluded.reason_code,
                notes = excluded.notes
            """,
            (
                process_id,
                competence,
                now,
                now,
                status,
                validated_pgdas_revenue_cents,
                validated_sped_lfe_revenue_cents,
                reason_code,
                notes,
            ),
        )


def list_accounting_study_conclusions(
    process_id: int,
) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                competence,
                created_at,
                updated_at,
                status,
                validated_pgdas_revenue_cents,
                validated_sped_lfe_revenue_cents,
                reason_code,
                notes
            FROM accounting_study_conclusions
            WHERE process_id = ?
            ORDER BY competence
            """,
            (process_id,),
        ).fetchall()

    return [
        {
            "competence": row["competence"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "status": row["status"],
            "validated_pgdas_revenue_cents": (
                row["validated_pgdas_revenue_cents"]
            ),
            "validated_sped_lfe_revenue_cents": (
                row["validated_sped_lfe_revenue_cents"]
            ),
            "reason_code": row["reason_code"],
            "notes": row["notes"],
        }
        for row in rows
    ]


def save_tax_profile(
    process_id: int,
    scenario: str,
    profile: dict[str, Any],
) -> None:
    now = utc_now()

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tax_profiles (
                process_id,
                scenario,
                created_at,
                updated_at,
                profile_json
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(process_id, scenario)
            DO UPDATE SET
                updated_at = excluded.updated_at,
                profile_json = excluded.profile_json
            """,
            (
                process_id,
                scenario,
                now,
                now,
                json.dumps(profile, ensure_ascii=False),
            ),
        )


def list_tax_profiles(
    process_id: int,
) -> dict[str, dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT scenario, profile_json
            FROM tax_profiles
            WHERE process_id = ?
            """,
            (process_id,),
        ).fetchall()

    return {
        row["scenario"]: json.loads(row["profile_json"])
        for row in rows
    }

def save_tax_calculation(
    process_id: int,
    annex: str,
    profile: str,
    calculation: dict[str, Any],
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tax_calculations (
                process_id,
                created_at,
                annex,
                profile,
                scenario,
                calculation_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                process_id,
                utc_now(),
                annex,
                profile,
                scenario,
                json.dumps(calculation, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def latest_tax_calculation(
    process_id: int,
    scenario: str | None = None,
) -> dict[str, Any] | None:
    with connect() as connection:
        if scenario is None:
            row = connection.execute(
                """
                SELECT calculation_json
                FROM tax_calculations
                WHERE process_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (process_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT calculation_json
                FROM tax_calculations
                WHERE process_id = ? AND scenario = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (process_id, scenario),
            ).fetchone()

    if row is None:
        return None

    return json.loads(row["calculation_json"])


def latest_tax_calculations(
    process_id: int,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT scenario, calculation_json
            FROM tax_calculations
            WHERE process_id = ?
            ORDER BY id DESC
            """,
            (process_id,),
        ).fetchall()

    for row in rows:
        if row["scenario"] not in result:
            result[row["scenario"]] = json.loads(
                row["calculation_json"]
            )

    return result

def save_legal_charge_calculation(
    process_id: int,
    update_date: str,
    calculation: dict[str, Any],
    scenario: str = "CONSERVATIVE_FISCAL_EXPOSURE",
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO legal_charge_calculations (
                process_id,
                created_at,
                update_date,
                scenario,
                calculation_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                process_id,
                utc_now(),
                update_date,
                scenario,
                json.dumps(calculation, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def latest_legal_charge_calculation(
    process_id: int,
    scenario: str | None = None,
) -> dict[str, Any] | None:
    with connect() as connection:
        if scenario is None:
            row = connection.execute(
                """
                SELECT calculation_json
                FROM legal_charge_calculations
                WHERE process_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (process_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT calculation_json
                FROM legal_charge_calculations
                WHERE process_id = ? AND scenario = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (process_id, scenario),
            ).fetchone()

    if row is None:
        return None

    return json.loads(row["calculation_json"])


def latest_legal_charge_calculations(
    process_id: int,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT scenario, calculation_json
            FROM legal_charge_calculations
            WHERE process_id = ?
            ORDER BY id DESC
            """,
            (process_id,),
        ).fetchall()

    for row in rows:
        if row["scenario"] not in result:
            result[row["scenario"]] = json.loads(
                row["calculation_json"]
            )

    return result

def save_client_report(
    process_id: int,
    update_date: str,
    report: dict[str, Any],
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO client_reports (
                process_id,
                created_at,
                update_date,
                report_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                process_id,
                utc_now(),
                update_date,
                json.dumps(report, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def latest_client_report(
    process_id: int,
) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT report_json
            FROM client_reports
            WHERE process_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (process_id,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(row["report_json"])


def register_stored_document(
    *,
    company_id: int,
    process_id: int,
    kind: str,
    competence: str,
    original_name: str,
    stored_path: str,
    sha256: str,
    size_bytes: int,
    status: str = "ACCEPTED",
) -> int:
    with connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO stored_documents (
                company_id, process_id, created_at, kind, competence,
                original_name, stored_path, sha256, size_bytes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id, process_id, utc_now(), kind, competence,
                original_name, stored_path, sha256, int(size_bytes), status,
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM stored_documents
            WHERE process_id = ? AND kind = ? AND sha256 = ?
            """,
            (process_id, kind, sha256),
        ).fetchone()
        if row is None:
            raise RuntimeError("Não foi possível registrar o documento.")
        return int(row["id"])


def list_stored_documents(process_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, company_id, process_id, created_at, kind, competence,
                   original_name, stored_path, sha256, size_bytes, status
            FROM stored_documents
            WHERE process_id = ?
            ORDER BY id DESC
            """,
            (process_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_stored_document(document_id: int) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, company_id, process_id, created_at, kind, competence,
                   original_name, stored_path, sha256, size_bytes, status
            FROM stored_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Documento {document_id} não encontrado.")
    return dict(row)


def database_status() -> dict[str, Any]:
    with connect() as connection:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        user_version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        company_count = connection.execute(
            "SELECT COUNT(*) FROM companies"
        ).fetchone()[0]
        process_count = connection.execute(
            "SELECT COUNT(*) FROM processes"
        ).fetchone()[0]
    return {
        "integrity": integrity,
        "user_version": int(user_version),
        "company_count": int(company_count),
        "process_count": int(process_count),
        "path": str(DB_PATH),
    }


init_db()
