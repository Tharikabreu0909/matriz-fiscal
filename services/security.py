from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any


def only_digits(value: str | None) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def is_valid_cnpj(value: str | None) -> bool:
    cnpj = only_digits(value)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False

    def digit(base: str, weights: list[int]) -> str:
        total = sum(int(number) * weight for number, weight in zip(base, weights))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = digit(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = digit(cnpj[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return cnpj[-2:] == first + second


def validate_cnpj(value: str | None) -> str:
    normalized = only_digits(value)
    if not is_valid_cnpj(normalized):
        raise ValueError("Informe um CNPJ válido.")
    return normalized


def normalize_name(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).upper()
    normalized = re.sub(r"\b(LTDA|ME|EPP|SA|S A|S\/A|COMERCIO|INDUSTRIA|SERVICOS?)\b", " ", normalized)
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def validate_malha_identity(
    company: dict[str, Any],
    malha: dict[str, Any],
) -> dict[str, Any]:
    contributor = malha.get("contributor", {})
    malha_cfdf = only_digits(contributor.get("cfdf"))
    company_registration = only_digits(company.get("state_registration"))

    company_names = [
        normalize_name(company.get("legal_name")),
        normalize_name(company.get("trade_name")),
    ]
    company_names = [value for value in company_names if value]
    malha_name = normalize_name(contributor.get("legal_name"))

    similarities = [
        SequenceMatcher(None, malha_name, candidate).ratio()
        for candidate in company_names
        if malha_name
    ]
    name_score = max(similarities, default=0.0)
    name_match = name_score >= 0.78

    registration_available = bool(malha_cfdf and company_registration)
    registration_match = (
        registration_available
        and malha_cfdf == company_registration
    )
    registration_mismatch = (
        registration_available
        and malha_cfdf != company_registration
    )

    if registration_match:
        match = True
        status = "MATCH_BY_REGISTRATION"
    elif registration_mismatch:
        match = False
        status = "REGISTRATION_MISMATCH"
    elif name_match:
        match = True
        status = "MATCH_BY_NAME"
    else:
        match = False
        status = "INSUFFICIENT_IDENTITY_MATCH"

    return {
        "match": match,
        "status": status,
        "name_match": name_match,
        "name_similarity": round(name_score, 4),
        "registration_match": registration_match,
        "registration_available": registration_available,
        "company": {
            "legal_name": company.get("legal_name", ""),
            "trade_name": company.get("trade_name", ""),
            "state_registration": company.get("state_registration", ""),
        },
        "malha": {
            "legal_name": contributor.get("legal_name", ""),
            "cfdf": contributor.get("cfdf", ""),
        },
    }
