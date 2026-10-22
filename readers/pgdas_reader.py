from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import hashlib
import re

import pdfplumber


MONEY_RE = re.compile(
    r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}"
)
MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])/\d{4}$")
DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
TRIBUTES = [
    "IRPJ",
    "CSLL",
    "COFINS",
    "PIS/PASEP",
    "INSS/CPP",
    "ICMS",
    "IPI",
    "ISS",
    "TOTAL",
]


class PgdasReaderError(RuntimeError):
    pass


def parse_money_to_cents(
    value: str | None,
) -> int | None:
    if value is None:
        return None

    cleaned = value.replace("\n", " ").strip()

    if not cleaned:
        return None

    match = MONEY_RE.search(cleaned)

    if not match:
        return None

    normalized = (
        match.group(0)
        .replace(".", "")
        .replace(",", ".")
    )
    return round(float(normalized) * 100)


def normalize_tribute(value: str) -> str:
    normalized = " ".join(
        (value or "").upper().split()
    )
    aliases = {
        "PIS": "PIS/PASEP",
        "PIS/PASEP": "PIS/PASEP",
        "TOTAL": "TOTAL",
    }
    return aliases.get(normalized, normalized)


def bool_from_pt(
    value: str | None,
) -> bool | None:
    if value is None:
        return None

    normalized = value.strip().lower()

    if normalized == "sim":
        return True

    if normalized in {"não", "nao"}:
        return False

    return None


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def format_basic_cnpj(full_cnpj: str) -> str:
    identifier = digits(full_cnpj)

    if len(identifier) < 8:
        return ""

    root = identifier[:8]
    return f"{root[:2]}.{root[2:5]}.{root[5:8]}"


def month_index(competence: str) -> int:
    month, year = map(int, competence.split("/"))
    return year * 12 + month - 1


def table_first_text(
    table: list[list[str | None]],
) -> str:
    return " ".join(
        str(cell or "")
        for row in table
        for cell in row
    )


def all_tables(
    pages: list[pdfplumber.page.Page],
) -> list[list[list[str | None]]]:
    return [
        table
        for page in pages
        for table in page.extract_tables()
        if table
    ]


def find_table_optional(
    tables: list[list[list[str | None]]],
    predicate: Callable[
        [list[list[str | None]]],
        bool,
    ],
) -> list[list[str | None]] | None:
    for table in tables:
        if predicate(table):
            return table

    return None


def require_table(
    tables: list[list[list[str | None]]],
    predicate: Callable[
        [list[list[str | None]]],
        bool,
    ],
    description: str,
) -> list[list[str | None]]:
    table = find_table_optional(
        tables,
        predicate,
    )

    if table is None:
        raise PgdasReaderError(
            f"Não foi possível localizar {description}."
        )

    return table


def parse_tax_vector(
    headers: list[str | None],
    values: list[str | None],
) -> dict[str, int]:
    result: dict[str, int] = {}

    for header, value in zip(headers, values):
        if not header:
            continue

        tribute = normalize_tribute(header)
        cents = parse_money_to_cents(value)

        if cents is not None:
            result[
                tribute.lower().replace("/", "_")
            ] = cents

    return result


def parse_previous_revenues(
    table: list[list[str | None]],
) -> list[dict[str, Any]]:
    internal: dict[str, int] = {}
    external: dict[str, int] = {}
    current_market: str | None = None

    for row in table:
        first = (row[0] or "").strip()

        if "Mercado Interno" in first:
            current_market = "internal"
            continue

        if "Mercado Externo" in first:
            current_market = "external"
            continue

        if current_market is None:
            continue

        for index in range(0, len(row), 2):
            competence = (
                row[index] or ""
            ).strip()
            amount = (
                row[index + 1]
                if index + 1 < len(row)
                else None
            )

            if not MONTH_RE.match(competence):
                continue

            cents = parse_money_to_cents(amount)

            if cents is None:
                continue

            target = (
                internal
                if current_market == "internal"
                else external
            )
            target[competence] = cents

    competences = sorted(
        set(internal) | set(external),
        key=month_index,
    )

    return [
        {
            "competence": competence,
            "internal_cents": internal.get(
                competence,
                0,
            ),
            "external_cents": external.get(
                competence,
                0,
            ),
            "total_cents": (
                internal.get(competence, 0)
                + external.get(competence, 0)
            ),
        }
        for competence in competences
    ]


def parse_revenue_summary(
    table: list[list[str | None]],
) -> dict[str, Any]:
    mapping = {
        "Receita Bruta do PA": "rpa",
        "(RBT12)": "rbt12",
        "(RBT12p)": "rbt12p",
        "(RBA)": "rba",
        "(RBAA)": "rbaa",
        (
            "Limite de receita bruta "
            "proporcionalizado"
        ): "proportionalized_limit",
    }
    result: dict[str, Any] = {}

    for row in table[1:]:
        label = (
            row[0] or ""
        ).replace("\n", " ").strip()
        key = None

        for marker, candidate in mapping.items():
            if marker in label:
                key = candidate
                break

        if key is None:
            continue

        values = [
            parse_money_to_cents(
                row[index]
                if index < len(row)
                else None
            )
            for index in range(1, 4)
        ]

        result[key] = {
            "internal_cents": values[0],
            "external_cents": values[1],
            "total_cents": values[2],
        }

    return result


def parse_activity_table(
    table: list[list[str | None]],
) -> dict[str, Any]:
    header_text = (
        table[0][0] or ""
    ).replace("\n", " ").strip()

    revenue_match = re.search(
        (
            r"Receita Bruta Informada:\s*R\$\s*"
            r"([0-9.,]+)"
        ),
        header_text,
        flags=re.I,
    )
    description_match = re.search(
        (
            r"Valor do Débito por Tributo para a "
            r"Atividade \(R\$\):\s*(.*?)\s*"
            r"Receita Bruta Informada:"
        ),
        header_text,
        flags=re.I,
    )

    tax_headers: list[str | None] = []
    tax_values: list[str | None] = []
    parcel_cents: int | None = None

    for row in table:
        normalized = [
            normalize_tribute(cell or "")
            for cell in row
        ]

        if (
            "IRPJ" in normalized
            and "TOTAL" in normalized
        ):
            tax_headers = list(row)
            continue

        if tax_headers and not tax_values:
            possible_values = [
                parse_money_to_cents(cell)
                for cell in row
            ]

            if sum(
                value is not None
                for value in possible_values
            ) >= 2:
                tax_values = list(row)

        first = (row[0] or "").strip()

        if first.startswith("Parcela"):
            parcel_cents = parse_money_to_cents(
                first
            )

    return {
        "description": (
            " ".join(
                description_match.group(1).split()
            )
            if description_match
            else ""
        ),
        "reported_revenue_cents": (
            parse_money_to_cents(
                revenue_match.group(1)
            )
            if revenue_match
            else None
        ),
        "taxes_cents": (
            parse_tax_vector(
                tax_headers,
                tax_values,
            )
            if tax_headers and tax_values
            else {}
        ),
        "parcel_revenue_cents": parcel_cents,
        "annex": None,
        "annex_status": (
            "NOT_EXPLICIT_IN_DOCUMENT"
        ),
    }


def parse_debt_sections(
    table: list[list[str | None]] | None,
) -> dict[str, dict[str, int]]:
    if table is None:
        return {}

    result: dict[str, dict[str, int]] = {}
    current_section: str | None = None
    headers: list[str | None] | None = None

    for row in table:
        first = (
            row[0] or ""
        ).replace("\n", " ").strip().lower()

        if "total do débito declarado" in first:
            current_section = "declared"
            headers = None
            continue

        if (
            "total do débito com "
            "exigibilidade suspensa"
        ) in first:
            current_section = "suspended"
            headers = None
            continue

        if "total do débito exigível" in first:
            current_section = "payable"
            headers = None
            continue

        normalized = [
            normalize_tribute(cell or "")
            for cell in row
        ]

        if (
            current_section
            and "IRPJ" in normalized
            and "TOTAL" in normalized
        ):
            headers = list(row)
            continue

        if current_section and headers:
            possible_values = [
                parse_money_to_cents(cell)
                for cell in row
            ]

            if sum(
                value is not None
                for value in possible_values
            ) >= 2:
                result[current_section] = (
                    parse_tax_vector(
                        headers,
                        list(row),
                    )
                )
                headers = None

    return result


def parse_three_row_tax_table(
    table: list[list[str | None]] | None,
) -> dict[str, int]:
    if (
        table is None
        or len(table) < 3
    ):
        return {}

    return parse_tax_vector(
        table[1],
        table[2],
    )


def empty_das() -> dict[str, Any]:
    return {
        "number": "",
        "due_date": "",
        "acceptance_deadline": "",
        "taxes_cents": {},
        "principal_cents": None,
        "fine_cents": None,
        "interest_cents": None,
        "total_cents": None,
    }


def parse_das_table(
    table: list[list[str | None]] | None,
) -> dict[str, Any]:
    if table is None:
        return empty_das()

    first_row = " ".join(
        str(cell or "")
        for cell in table[0]
    )

    number_match = re.search(
        r"Número:\s*(\d+)",
        first_row,
    )
    due_match = re.search(
        (
            r"Data de Vencimento:\s*"
            r"(\d{2}/\d{2}/\d{4})"
        ),
        first_row,
    )
    acceptance_match = re.search(
        (
            r"Data limite para acolhimento:\s*"
            r"(\d{2}/\d{2}/\d{4})"
        ),
        first_row,
    )

    tax_values: dict[str, int] = {}
    financial_values: dict[str, int] = {}

    for row in table[1:]:
        for index in range(0, len(row), 2):
            label = (
                row[index] or ""
            ).strip()
            value = (
                row[index + 1]
                if index + 1 < len(row)
                else None
            )
            cents = parse_money_to_cents(value)

            if not label or cents is None:
                continue

            normalized = normalize_tribute(label)
            financial_label = label.lower()

            if financial_label in {
                "principal",
                "multa",
                "juros",
                "total",
            }:
                financial_values[
                    financial_label
                ] = cents
            elif (
                normalized in TRIBUTES
                and normalized != "TOTAL"
            ):
                tax_values[
                    normalized.lower().replace(
                        "/",
                        "_",
                    )
                ] = cents

    return {
        "number": (
            number_match.group(1)
            if number_match
            else ""
        ),
        "due_date": (
            due_match.group(1)
            if due_match
            else ""
        ),
        "acceptance_deadline": (
            acceptance_match.group(1)
            if acceptance_match
            else ""
        ),
        "taxes_cents": tax_values,
        "principal_cents": (
            financial_values.get("principal")
        ),
        "fine_cents": (
            financial_values.get("multa")
        ),
        "interest_cents": (
            financial_values.get("juros")
        ),
        "total_cents": (
            financial_values.get("total")
        ),
    }


def parse_destinations_and_payment(
    tables: list[list[list[str | None]]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    destination_rows: list[dict[str, Any]] = []
    payment: dict[str, Any] | None = None
    destination_section = False
    payment_section = False

    for table in tables:
        for row in table:
            row_text = " ".join(
                str(cell or "")
                for cell in row
            )
            first = (row[0] or "").strip()

            if (
                "Ente Federativo de Destino"
                in row_text
            ):
                destination_section = True
                continue

            if (
                "Informações da Arrecadação"
                in row_text
            ):
                payment_section = True
                destination_section = False
                continue

            if (
                "Data de Pagamento"
                in row_text
                and "Valor Pago" in row_text
            ):
                payment_section = True
                destination_section = False
                continue

            compact_cells = [
                str(cell).strip()
                for cell in row
                if cell is not None
                and str(cell).strip()
            ]

            if payment_section:
                if (
                    compact_cells
                    and DATE_RE.fullmatch(
                        compact_cells[0]
                    )
                ):
                    payment = {
                        "payment_date": (
                            compact_cells[0]
                        ),
                        "bank_agency": (
                            compact_cells[1]
                            if len(compact_cells) > 1
                            else ""
                        ),
                        "paid_cents": (
                            parse_money_to_cents(
                                compact_cells[2]
                                if len(compact_cells) > 2
                                else None
                            )
                        ),
                    }
                continue

            if destination_section:
                tribute = normalize_tribute(
                    compact_cells[0]
                    if compact_cells
                    else ""
                )
                cents = parse_money_to_cents(
                    compact_cells[1]
                    if len(compact_cells) > 1
                    else None
                )
                destination = (
                    compact_cells[2]
                    if len(compact_cells) > 2
                    else ""
                )

                if (
                    tribute in TRIBUTES
                    and tribute != "TOTAL"
                    and cents is not None
                ):
                    destination_rows.append({
                        "tribute": tribute,
                        "value_cents": cents,
                        "destination": destination,
                    })

    return destination_rows, payment


def detect_document_type(
    full_text: str,
) -> str:
    if "Extrato do Simples Nacional" in full_text:
        return "PGDAS_EXTRACT"

    if (
        "Programa Gerador do Documento de Arrecadação"
        in full_text
        and "Declaratório" in full_text
    ):
        return "PGDAS_DECLARATION"

    raise PgdasReaderError(
        "O PDF não foi reconhecido como Extrato ou "
        "Declaração do PGDAS-D."
    )


def extract_metadata(
    texts: list[str],
    full_text: str,
    document_type: str,
) -> dict[str, Any]:
    first_page_text = texts[0] if texts else ""

    if document_type == "PGDAS_EXTRACT":
        generated_match = re.search(
            (
                r"Gerado em\s*"
                r"(\d{2}/\d{2}/\d{4}\s+"
                r"\d{2}:\d{2}:\d{2})"
            ),
            full_text,
        )
        assessed_match = re.search(
            (
                r"Apurado em\s*"
                r"(\d{2}/\d{2}/\d{4}\s+"
                r"\d{2}:\d{2}:\d{2})"
            ),
            full_text,
        )
        assessment_type_match = re.search(
            (
                r"\bApuração\s+"
                r"(Retificadora|Original)\b"
            ),
            full_text,
            flags=re.I,
        )
        version_match = re.search(
            (
                r"PGDAS-D\s+2018\s+"
                r"Versão\s+([0-9.]+)"
            ),
            full_text,
        )
        basic_cnpj_match = re.search(
            r"CNPJ Básico:\s*([0-9.]+)",
            full_text,
        )
        full_cnpj_match = re.search(
            (
                r"CNPJ Estabelecimento:\s*"
                r"([0-9./-]+)"
            ),
            full_text,
        )
        legal_name_match = re.search(
            (
                r"Nome Empresarial:\s*"
                r"(.+?)$"
            ),
            first_page_text,
            flags=re.M | re.I,
        )
        opening_date_match = re.search(
            (
                r"Data de Abertura:\s*"
                r"(\d{2}/\d{2}/\d{4})"
            ),
            full_text,
            flags=re.I,
        )
        accrual_regime_match = re.search(
            (
                r"Regime de Apuração:\s*"
                r"([^\n]+?)"
                r"(?=\s+Optante pelo "
                r"Simples Nacional:)"
            ),
            full_text,
            flags=re.I,
        )
        optant_match = re.search(
            (
                r"Optante pelo Simples Nacional:"
                r"\s*(Sim|Não|Nao)"
            ),
            full_text,
            flags=re.I,
        )
        assessment_id_match = re.search(
            (
                r"2\)\s*Informações da Apuração"
                r"\s+(\d+)"
            ),
            full_text,
        )
        pa_match = re.search(
            (
                r"Período de Apuração \(PA\):"
                r"\s*(\d{2}/\d{4})"
            ),
            full_text,
        )

        return {
            "generated_at": (
                generated_match.group(1)
                if generated_match
                else ""
            ),
            "assessed_at": (
                assessed_match.group(1)
                if assessed_match
                else ""
            ),
            "assessment_type": (
                f"APURAÇÃO "
                f"{assessment_type_match.group(1).upper()}"
                if assessment_type_match
                else ""
            ),
            "pgdas_version": (
                version_match.group(1)
                if version_match
                else ""
            ),
            "basic_cnpj": (
                basic_cnpj_match.group(1)
                if basic_cnpj_match
                else (
                    format_basic_cnpj(
                        full_cnpj_match.group(1)
                    )
                    if full_cnpj_match
                    else ""
                )
            ),
            "legal_name": (
                legal_name_match.group(1).strip()
                if legal_name_match
                else ""
            ),
            "opening_date": (
                opening_date_match.group(1)
                if opening_date_match
                else ""
            ),
            "accrual_regime": (
                accrual_regime_match.group(1).strip()
                if accrual_regime_match
                else ""
            ),
            "simple_national_optant": (
                bool_from_pt(
                    optant_match.group(1)
                )
                if optant_match
                else None
            ),
            "assessment_id": (
                assessment_id_match.group(1)
                if assessment_id_match
                else ""
            ),
            "period": (
                pa_match.group(1)
                if pa_match
                else ""
            ),
            "transmitted_at": "",
        }

    transmission_match = re.search(
        (
            r"Data e horário da transmissão "
            r"da Declaração:\s*"
            r"(\d{2}/\d{2}/\d{4}\s+"
            r"\d{2}:\d{2}:\d{2})"
        ),
        full_text,
        flags=re.I,
    )
    assessment_type_match = re.search(
        (
            r"Declaração\s+"
            r"(Retificadora|Original)"
        ),
        full_text,
        flags=re.I,
    )
    full_cnpj_match = re.search(
        (
            r"CNPJ Matriz:\s*"
            r"([0-9./-]+)"
        ),
        full_text,
        flags=re.I,
    )
    legal_name_match = re.search(
        r"Nome empresarial:\s*(.+?)$",
        first_page_text,
        flags=re.M | re.I,
    )
    opening_date_match = re.search(
        (
            r"Data de abertura no CNPJ:\s*"
            r"(\d{2}/\d{2}/\d{4})"
        ),
        full_text,
        flags=re.I,
    )
    accrual_regime_match = re.search(
        (
            r"Regime de Apuração:\s*"
            r"(.+?)$"
        ),
        first_page_text,
        flags=re.M | re.I,
    )
    optant_match = re.search(
        (
            r"Optante pelo Simples Nacional:"
            r"\s*(Sim|Não|Nao)"
        ),
        full_text,
        flags=re.I,
    )
    assessment_id_match = re.search(
        (
            r"N[ºo°]\s*da Declaração:\s*"
            r"(\d+)"
        ),
        full_text,
        flags=re.I,
    )
    period_range_match = re.search(
        (
            r"Período de Apuração:\s*"
            r"(\d{2})/(\d{2})/(\d{4})"
            r"\s+a\s+"
            r"(\d{2})/(\d{2})/(\d{4})"
        ),
        full_text,
        flags=re.I,
    )

    period = ""

    if period_range_match:
        period = (
            f"{period_range_match.group(2)}/"
            f"{period_range_match.group(3)}"
        )

    return {
        "generated_at": "",
        "assessed_at": "",
        "assessment_type": (
            f"DECLARAÇÃO "
            f"{assessment_type_match.group(1).upper()}"
            if assessment_type_match
            else ""
        ),
        "pgdas_version": "",
        "basic_cnpj": (
            format_basic_cnpj(
                full_cnpj_match.group(1)
            )
            if full_cnpj_match
            else ""
        ),
        "legal_name": (
            legal_name_match.group(1).strip()
            if legal_name_match
            else ""
        ),
        "opening_date": (
            opening_date_match.group(1)
            if opening_date_match
            else ""
        ),
        "accrual_regime": (
            accrual_regime_match.group(1).strip()
            if accrual_regime_match
            else ""
        ),
        "simple_national_optant": (
            bool_from_pt(
                optant_match.group(1)
            )
            if optant_match
            else None
        ),
        "assessment_id": (
            assessment_id_match.group(1)
            if assessment_id_match
            else ""
        ),
        "period": period,
        "transmitted_at": (
            transmission_match.group(1)
            if transmission_match
            else ""
        ),
    }


def read_pgdas_pdf(
    pdf_path: str | Path,
) -> dict[str, Any]:
    path = Path(pdf_path)
    file_hash = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    with pdfplumber.open(path) as pdf:
        pages = list(pdf.pages)
        texts = [
            page.extract_text() or ""
            for page in pages
        ]
        full_text = "\n".join(texts)
        tables = all_tables(pages)

    document_type = detect_document_type(
        full_text
    )
    metadata = extract_metadata(
        texts,
        full_text,
        document_type,
    )

    if not metadata["period"]:
        raise PgdasReaderError(
            "O período de apuração não foi reconhecido."
        )

    if not metadata["basic_cnpj"]:
        raise PgdasReaderError(
            "O CNPJ do contribuinte não foi reconhecido."
        )

    revenue_table = require_table(
        tables,
        lambda table: (
            "Total de Receitas Brutas"
            in table_first_text(table)
            and "RBT12"
            in table_first_text(table)
        ),
        "o quadro de receitas e RBT12",
    )
    history_table = require_table(
        tables,
        lambda table: (
            "2.2.1) Mercado Interno"
            in table_first_text(table)
            and "2.2.2) Mercado Externo"
            in table_first_text(table)
        ),
        "o histórico de receitas anteriores",
    )
    establishment_table = require_table(
        tables,
        lambda table: (
            "CNPJ Estabelecimento:"
            in table_first_text(table)
        ),
        "a identificação do estabelecimento",
    )

    activity_tables = [
        table
        for table in tables
        if (
            "Valor do Débito por Tributo "
            "para a Atividade"
        ) in table_first_text(table)
    ]

    establishment_debt_table = (
        find_table_optional(
            tables,
            lambda table: (
                (
                    "Informações por Estabelecimento"
                    in table_first_text(table)
                    or
                    "Totais do Estabelecimento"
                    in table_first_text(table)
                )
                and
                "Total do Débito Exigível"
                in table_first_text(table)
            ),
        )
    )

    company_declared_table = (
        find_table_optional(
            tables,
            lambda table: (
                (
                    "Total do Débito Declarado "
                    "(exigível + suspenso) (R$)"
                )
                in table_first_text(table)
                and len(table) == 3
            ),
        )
    )
    company_suspended_table = (
        find_table_optional(
            tables,
            lambda table: (
                (
                    "Total do Débito com "
                    "Exigibilidade Suspensa (R$)"
                )
                in table_first_text(table)
                and len(table) == 3
            ),
        )
    )
    company_payable_table = (
        find_table_optional(
            tables,
            lambda table: (
                "Total do Débito Exigível (R$)"
                in table_first_text(table)
                and len(table) == 3
            ),
        )
    )
    das_table = find_table_optional(
        tables,
        lambda table: (
            "Número:"
            in table_first_text(table)
            and "Principal"
            in table_first_text(table)
            and "Juros"
            in table_first_text(table)
        ),
    )

    revenue_summary = parse_revenue_summary(
        revenue_table
    )
    previous_revenues = parse_previous_revenues(
        history_table
    )

    if not previous_revenues:
        raise PgdasReaderError(
            "O histórico de receitas foi localizado, "
            "mas nenhum mês pôde ser lido."
        )

    establishment_text = table_first_text(
        establishment_table
    )
    establishment_cnpj_match = re.search(
        (
            r"CNPJ Estabelecimento:\s*"
            r"([0-9./-]+)"
        ),
        establishment_text,
    )
    municipality_match = re.search(
        (
            r"Município:\s*"
            r"([A-ZÀ-Ü ]+?)"
            r"(?=\s+UF:|$)"
        ),
        establishment_text,
    )
    uf_match = re.search(
        r"UF:\s*([A-Z]{2})",
        establishment_text,
    )
    sublimit_match = re.search(
        (
            r"Sublimite de Receita Anual "
            r"\(R\$\):\s*([0-9.,]+)"
        ),
        establishment_text,
    )
    blocked_match = re.search(
        (
            r"Impedido de recolher ICMS/ISS "
            r"no DAS:\s*(Sim|Não|Nao)"
        ),
        establishment_text,
        flags=re.I,
    )

    if sublimit_match is None:
        global_sublimit_match = re.search(
            (
                r"Sublimite de Receita Anual "
                r"\(R\$\):\s*([0-9.,]+)"
            ),
            full_text,
        )
        sublimit_match = global_sublimit_match

    if blocked_match is None:
        global_blocked_match = re.search(
            (
                r"Impedido de recolher ICMS/ISS "
                r"no DAS:\s*(Sim|Não|Nao)"
            ),
            full_text,
            flags=re.I,
        )
        blocked_match = global_blocked_match

    activities = [
        parse_activity_table(table)
        for table in activity_tables
    ]
    establishment_debts = (
        parse_debt_sections(
            establishment_debt_table
        )
    )
    company_debts = {
        "declared": (
            parse_three_row_tax_table(
                company_declared_table
            )
        ),
        "suspended": (
            parse_three_row_tax_table(
                company_suspended_table
            )
        ),
        "payable": (
            parse_three_row_tax_table(
                company_payable_table
            )
        ),
    }
    das = parse_das_table(das_table)
    destination_rows, payment = (
        parse_destinations_and_payment(
            tables
        )
    )

    rbt12_document = (
        revenue_summary.get(
            "rbt12",
            {},
        ).get("total_cents")
    )
    last_12 = previous_revenues[-12:]
    rbt12_recomputed = sum(
        item["total_cents"]
        for item in last_12
    )

    history_indexes = [
        month_index(item["competence"])
        for item in previous_revenues
    ]
    expected_indexes = (
        list(
            range(
                history_indexes[0],
                history_indexes[-1] + 1,
            )
        )
        if history_indexes
        else []
    )
    history_consecutive = (
        history_indexes == expected_indexes
    )

    current_revenue = (
        revenue_summary.get(
            "rpa",
            {},
        ).get("total_cents")
    )
    das_total = das.get("total_cents")
    payable_total = company_debts.get(
        "payable",
        {},
    ).get("total")
    observed_debt = (
        das_total
        if das_total is not None
        else payable_total
    )
    tax_sum = sum(
        das.get(
            "taxes_cents",
            {},
        ).values()
    )

    observed_rate = (
        observed_debt / current_revenue
        if (
            observed_debt is not None
            and current_revenue
        )
        else None
    )

    full_cnpjs = [
        (
            establishment_cnpj_match.group(1)
            if establishment_cnpj_match
            else ""
        )
    ]

    has_das = das_table is not None
    has_payment = payment is not None

    return {
        "reader": {
            "name": "checkfiscal-pgdas-reader",
            "version": "2.0.0",
            "strategy": (
                "STANDARD_PGDAS_DOCUMENT_CLASSIFIER"
            ),
        },
        "source_document": {
            "file_name": path.name,
            "sha256": file_hash,
            "page_count": len(pages),
            "document_type": document_type,
            "generated_at": metadata[
                "generated_at"
            ],
            "assessed_at": metadata[
                "assessed_at"
            ],
            "transmitted_at": metadata[
                "transmitted_at"
            ],
            "assessment_type": metadata[
                "assessment_type"
            ],
            "pgdas_version": metadata[
                "pgdas_version"
            ],
        },
        "taxpayer": {
            "basic_cnpj": metadata[
                "basic_cnpj"
            ],
            "legal_name": metadata[
                "legal_name"
            ],
            "opening_date": metadata[
                "opening_date"
            ],
            "accrual_regime": metadata[
                "accrual_regime"
            ],
            "simple_national_optant": (
                metadata[
                    "simple_national_optant"
                ]
            ),
            "full_cnpjs_found": [
                value
                for value in full_cnpjs
                if value
            ],
        },
        "assessment": {
            "assessment_id": metadata[
                "assessment_id"
            ],
            "period": metadata["period"],
            "revenue_summary": (
                revenue_summary
            ),
            "previous_revenues": (
                previous_revenues
            ),
            "payroll_history_status": (
                "NONE"
                if re.search(
                    (
                        r"2\.3\)\s*Folha de "
                        r"Salários Anteriores.*?Nenhuma"
                    ),
                    full_text,
                    flags=re.S,
                )
                else "PRESENT_OR_UNKNOWN"
            ),
            "factor_r": (
                "NOT_APPLICABLE"
                if (
                    "Fator r = Não se aplica"
                    in full_text
                )
                else "PRESENT_OR_UNKNOWN"
            ),
            "fixed_values": (
                "NOT_APPLICABLE"
                if re.search(
                    (
                        r"2\.5\)\s*Valores Fixos"
                        r"\s+Não se aplica"
                    ),
                    full_text,
                )
                else "PRESENT_OR_UNKNOWN"
            ),
        },
        "establishments": [{
            "cnpj": (
                establishment_cnpj_match.group(1)
                if establishment_cnpj_match
                else ""
            ),
            "municipality": (
                municipality_match.group(1).strip()
                if municipality_match
                else ""
            ),
            "uf": (
                uf_match.group(1)
                if uf_match
                else ""
            ),
            "annual_revenue_sublimit_cents": (
                parse_money_to_cents(
                    sublimit_match.group(1)
                )
                if sublimit_match
                else None
            ),
            "blocked_from_icms_iss_in_das": (
                bool_from_pt(
                    blocked_match.group(1)
                )
                if blocked_match
                else None
            ),
            "activities": activities,
            "debts": establishment_debts,
        }],
        "company_debts": company_debts,
        "das": {
            **das,
            "recognized_paid_das_for_pa": (
                []
                if (
                    "Não foram identificados DAS "
                    "pagos para este PA"
                    in full_text
                )
                else None
            ),
            "destinations": destination_rows,
            "payment": payment,
        },
        "document_capabilities": {
            "usable_for_analysis": True,
            "usable_for_reflection_coverage": True,
            "contains_das": has_das,
            "contains_payment": has_payment,
            "preferred_for_due_date": has_das,
            "description": (
                "Extrato completo com DAS e arrecadação."
                if document_type == "PGDAS_EXTRACT"
                else (
                    "Declaração aceita para receitas, "
                    "RBT12 e débitos. O vencimento será "
                    "obtido de outro extrato ou pela regra "
                    "padrão quando necessário."
                )
            ),
        },
        "coverage": {
            "history_start": (
                previous_revenues[0][
                    "competence"
                ]
                if previous_revenues
                else ""
            ),
            "history_end": (
                previous_revenues[-1][
                    "competence"
                ]
                if previous_revenues
                else ""
            ),
            "history_month_count": len(
                previous_revenues
            ),
            "history_consecutive": (
                history_consecutive
            ),
            (
                "has_previous_12_months_"
                "for_current_pa"
            ): (
                len(previous_revenues) >= 12
                and history_consecutive
            ),
            "has_future_months_after_pa": any(
                month_index(item["competence"])
                > month_index(metadata["period"])
                for item in previous_revenues
            ),
        },
        "derived_metrics": {
            (
                "observed_das_over_"
                "current_revenue_rate"
            ): observed_rate,
            "rate_status": (
                "DERIVED_NOT_EXPLICIT_IN_DOCUMENT"
            ),
            "annex": None,
            "annex_status": (
                "NOT_EXPLICIT_IN_DOCUMENT"
            ),
        },
        "validations": {
            "rbt12_document_cents": (
                rbt12_document
            ),
            "rbt12_recomputed_cents": (
                rbt12_recomputed
            ),
            "rbt12_matches": (
                rbt12_document
                == rbt12_recomputed
            ),
            "das_tax_sum_cents": (
                tax_sum
                if has_das
                else None
            ),
            "das_total_cents": (
                das_total
            ),
            "das_tax_sum_matches_total": (
                tax_sum == das_total
                if has_das
                else None
            ),
            "payment_matches_das_total": (
                payment is not None
                and payment.get(
                    "paid_cents"
                ) == das_total
            ) if has_das else None,
            (
                "current_revenue_matches_"
                "activity_total"
            ): (
                current_revenue
                == sum(
                    (
                        activity.get(
                            "reported_revenue_cents"
                        )
                        or 0
                    )
                    for activity in activities
                )
            ),
            "essential_fields_complete": all([
                metadata["period"],
                metadata["basic_cnpj"],
                current_revenue is not None,
                rbt12_document is not None,
                bool(previous_revenues),
            ]),
        },
    }
