from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


BCB_SELIC_SERIES = 4390


class LegalChargesError(ValueError):
    pass


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise LegalChargesError(
            "Data de atualização inválida."
        ) from error


def parse_br_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as error:
        raise LegalChargesError(
            "Data de vencimento inválida."
        ) from error


def competence_parts(competence: str) -> tuple[int, int]:
    month, year = map(int, competence.split("/"))
    return year, month


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def standard_due_date(competence: str) -> date:
    """
    Regra padrão: dia 20 do mês subsequente.
    Quando o dia 20 cai em sábado ou domingo, avança para segunda.

    Feriados bancários e prorrogações extraordinárias precisam ser
    conferidos por fonte oficial ou pelo vencimento presente no PGDAS.
    """
    year, month = competence_parts(competence)
    due_year, due_month = next_month(year, month)
    due = date(due_year, due_month, 20)

    while due.weekday() >= 5:
        due += timedelta(days=1)

    return due


def document_due_dates(
    pgdas_documents: list[dict[str, Any]],
) -> dict[str, date]:
    result: dict[str, date] = {}

    for pgdas in pgdas_documents:
        competence = (
            pgdas.get("assessment", {}).get("period", "")
        )
        due_text = pgdas.get("das", {}).get("due_date", "")

        if competence and due_text:
            try:
                result[competence] = parse_br_date(due_text)
            except LegalChargesError:
                continue

    return result


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_sequence(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    year, month = start_year, start_month

    while (year, month) <= (end_year, end_month):
        result.append((year, month))
        year, month = next_month(year, month)

    return result


def fetch_bcb_monthly_selic(
    start_date: date,
    end_date: date,
    timeout_seconds: int = 15,
) -> dict[str, Decimal]:
    if start_date > end_date:
        return {}

    query = urlencode({
        "formato": "json",
        "dataInicial": start_date.strftime("%d/%m/%Y"),
        "dataFinal": end_date.strftime("%d/%m/%Y"),
    })
    url = (
        "https://api.bcb.gov.br/dados/serie/"
        f"bcdata.sgs.{BCB_SELIC_SERIES}/dados?{query}"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "CheckFiscal/1.11",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as error:
        raise LegalChargesError(
            "Não foi possível consultar a Selic oficial no Banco "
            "Central. Verifique a internet e tente novamente."
        ) from error

    rates: dict[str, Decimal] = {}

    for row in payload:
        value_date = datetime.strptime(
            row["data"],
            "%d/%m/%Y",
        ).date()
        rates[month_key(value_date)] = Decimal(
            row["valor"].replace(",", ".")
        )

    return rates


def fine_rate(days_late: int) -> Decimal:
    if days_late <= 0:
        return Decimal("0")

    return min(
        Decimal(days_late) * Decimal("0.0033"),
        Decimal("0.20"),
    )


def interest_rate(
    due_date: date,
    update_date: date,
    monthly_selic: dict[str, Decimal],
) -> Decimal:
    if update_date <= due_date:
        return Decimal("0")

    if (
        due_date.year == update_date.year
        and due_date.month == update_date.month
    ):
        return Decimal("0")

    start_year, start_month = next_month(
        due_date.year,
        due_date.month,
    )

    previous_month_end = (
        update_date.replace(day=1)
        - timedelta(days=1)
    )
    required_months = month_sequence(
        start_year,
        start_month,
        previous_month_end.year,
        previous_month_end.month,
    )

    rate = Decimal("0")
    missing: list[str] = []

    for year, month in required_months:
        key = f"{year:04d}-{month:02d}"
        if key not in monthly_selic:
            missing.append(key)
            continue
        rate += monthly_selic[key] / Decimal("100")

    if missing:
        raise LegalChargesError(
            "A série Selic não retornou todos os meses necessários: "
            + ", ".join(missing)
        )

    # Mês do pagamento/atualização.
    rate += Decimal("0.01")
    return rate


def cents_times_rate(
    cents: int,
    rate: Decimal,
) -> int:
    return int(
        (Decimal(cents) * rate).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def selic_query_range(
    impacts: list[dict[str, Any]],
    due_dates: dict[str, date],
    update_date: date,
) -> tuple[date, date] | None:
    starts: list[date] = []

    for impact in impacts:
        if impact.get("difference_cents", 0) <= 0:
            continue

        competence = impact["competence"]
        due = due_dates.get(
            competence,
            standard_due_date(competence),
        )

        if (
            update_date > due
            and (
                update_date.year,
                update_date.month,
            ) != (
                due.year,
                due.month,
            )
        ):
            first_year, first_month = next_month(
                due.year,
                due.month,
            )
            starts.append(date(first_year, first_month, 1))

    if not starts:
        return None

    end = update_date.replace(day=1) - timedelta(days=1)
    return min(starts), end


def calculate_legal_charges(
    tax_result: dict[str, Any],
    pgdas_documents: list[dict[str, Any]],
    update_date_text: str,
    monthly_selic: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    update_date = parse_iso_date(update_date_text)
    impacts = tax_result.get("visible_impacts", [])
    known_due_dates = document_due_dates(pgdas_documents)

    due_dates = {
        impact["competence"]: known_due_dates.get(
            impact["competence"],
            standard_due_date(impact["competence"]),
        )
        for impact in impacts
    }

    query_range = selic_query_range(
        impacts,
        due_dates,
        update_date,
    )

    if monthly_selic is None:
        monthly_selic = (
            fetch_bcb_monthly_selic(
                query_range[0],
                query_range[1],
            )
            if query_range
            else {}
        )

    rows: list[dict[str, Any]] = []
    principal_total = 0
    fine_total = 0
    interest_total = 0
    due_date_estimate_count = 0

    for impact in impacts:
        principal = max(
            0,
            int(impact.get("difference_cents", 0)),
        )

        if principal == 0:
            continue

        competence = impact["competence"]
        due_from_document = competence in known_due_dates
        due = due_dates[competence]

        if not due_from_document:
            due_date_estimate_count += 1

        days_late = max(
            0,
            (update_date - due).days,
        )
        applied_fine_rate = fine_rate(days_late)
        applied_interest_rate = interest_rate(
            due,
            update_date,
            monthly_selic,
        )

        fine_cents = cents_times_rate(
            principal,
            applied_fine_rate,
        )
        interest_cents = cents_times_rate(
            principal,
            applied_interest_rate,
        )
        total = principal + fine_cents + interest_cents

        principal_total += principal
        fine_total += fine_cents
        interest_total += interest_cents

        rows.append({
            "competence": competence,
            "classification": impact.get(
                "classification",
                "",
            ),
            "principal_cents": principal,
            "due_date": due.isoformat(),
            "due_date_source": (
                "PGDAS_DOCUMENT"
                if due_from_document
                else "STANDARD_ESTIMATE"
            ),
            "update_date": update_date.isoformat(),
            "days_late": days_late,
            "fine_rate": str(applied_fine_rate),
            "fine_cents": fine_cents,
            "interest_rate": str(
                applied_interest_rate
            ),
            "interest_cents": interest_cents,
            "total_cents": total,
        })

    warnings = [
        (
            "Multa de mora calculada a 0,33% ao dia, "
            "limitada a 20%."
        ),
        (
            "Juros calculados pela Selic mensal do Banco Central, "
            "somada desde o mês seguinte ao vencimento até o mês "
            "anterior à atualização, mais 1% no mês da atualização."
        ),
    ]

    if due_date_estimate_count:
        warnings.append(
            f"{due_date_estimate_count} vencimento(s) foram estimados "
            "pela regra padrão do dia 20. Feriados bancários, "
            "calamidades e prorrogações especiais podem alterar a data."
        )

    return {
        "source": {
            "selic_series": BCB_SELIC_SERIES,
            "selic_provider": "BANCO_CENTRAL_DO_BRASIL",
            "update_date": update_date.isoformat(),
        },
        "summary": {
            "principal_cents": principal_total,
            "fine_cents": fine_total,
            "interest_cents": interest_total,
            "total_cents": (
                principal_total
                + fine_total
                + interest_total
            ),
            "competence_count": len(rows),
            "estimated_due_date_count": (
                due_date_estimate_count
            ),
        },
        "rows": rows,
        "warnings": warnings,
    }
