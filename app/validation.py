"""Shared field validators for the patient demographic data model.

These run on every API write so the voice agent is never the only line of defense.
Stored forms are normalized (e.g. phones as 10 digits, states as uppercase)
so lookups and the later telephony layer can compare values reliably.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum

from pydantic_core import PydanticCustomError

# Letters, optional internal spaces / hyphens / apostrophes. 1–50 chars.
# Allows O'Brien, Mary-Anne, and Ann Marie; rejects digits and trailing punctuation.
_NAME_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ '\-](?=[A-Za-z])){0,49}$")
_FULL_NAME_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ '\-](?=[A-Za-z])){0,99}$")
_CITY_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ .'\-](?=[A-Za-z])){0,99}$")
_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
_MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,50}$")
_LANGUAGE_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ \-](?=[A-Za-z])){0,49}$")

# 50 states + DC (standard USPS set used by U.S. healthcare intake).
US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


class Sex(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE_TO_ANSWER = "Decline to Answer"


# Voice / free-text aliases map onto the four allowed enum values.
_SEX_ALIASES = {
    "male": Sex.MALE,
    "m": Sex.MALE,
    "man": Sex.MALE,
    "female": Sex.FEMALE,
    "f": Sex.FEMALE,
    "woman": Sex.FEMALE,
    "other": Sex.OTHER,
    "nonbinary": Sex.OTHER,
    "non-binary": Sex.OTHER,
    "non binary": Sex.OTHER,
    "decline to answer": Sex.DECLINE_TO_ANSWER,
    "decline": Sex.DECLINE_TO_ANSWER,
    "prefer not to say": Sex.DECLINE_TO_ANSWER,
    "prefer not to answer": Sex.DECLINE_TO_ANSWER,
}


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_person_name(value: str, field: str = "name", *, max_len: int = 50) -> str:
    cleaned = _clean(value)
    pattern = _FULL_NAME_RE if max_len > 50 else _NAME_RE
    if not cleaned or len(cleaned) > max_len or not pattern.match(cleaned):
        raise PydanticCustomError(
            "invalid_name",
            "{field} must be 1–{max_len} characters and contain only letters, spaces, hyphens, or apostrophes",
            {"field": field, "max_len": max_len},
        )
    return cleaned


def parse_date_of_birth(value: str | date) -> date:
    """Require MM/DD/YYYY, a real calendar date, and not in the future."""
    if isinstance(value, date) and not isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.strptime(raw, "%m/%d/%Y").date()
        except ValueError as exc:
            raise PydanticCustomError(
                "invalid_dob",
                "date_of_birth must be a valid calendar date in MM/DD/YYYY format",
                {},
            ) from exc

    if parsed > date.today():
        raise PydanticCustomError(
            "future_dob",
            "date_of_birth cannot be in the future",
            {},
        )
    return parsed


def format_date_of_birth(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def normalize_sex(value: str | Sex) -> Sex:
    if isinstance(value, Sex):
        return value
    key = _clean(str(value)).lower()
    mapped = _SEX_ALIASES.get(key)
    if mapped is None:
        try:
            return Sex(value)
        except ValueError as exc:
            raise PydanticCustomError(
                "invalid_sex",
                "sex must be one of: Male, Female, Other, Decline to Answer",
                {},
            ) from exc
    return mapped


def normalize_us_phone(value: str, field: str = "phone_number") -> str:
    """Accept common US formats; persist as a 10-digit NANP number."""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    # NANP: NXX-NXX-XXXX where N is 2–9.
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        raise PydanticCustomError(
            "invalid_phone",
            "{field} must be a valid U.S. 10-digit phone number",
            {"field": field},
        )
    return digits


def normalize_state(value: str) -> str:
    code = _clean(value).upper()
    if code not in US_STATE_ABBREVIATIONS:
        raise PydanticCustomError(
            "invalid_state",
            "state must be a valid 2-letter U.S. state abbreviation",
            {},
        )
    return code


def normalize_zip_code(value: str) -> str:
    cleaned = _clean(value)
    if not _ZIP_RE.match(cleaned):
        raise PydanticCustomError(
            "invalid_zip",
            "zip_code must be a 5-digit ZIP or ZIP+4 (12345 or 12345-6789)",
            {},
        )
    return cleaned


def normalize_city(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned or len(cleaned) > 100 or not _CITY_RE.match(cleaned):
        raise PydanticCustomError(
            "invalid_city",
            "city must be 1–100 characters and contain only letters, spaces, periods, hyphens, or apostrophes",
            {},
        )
    return cleaned


def normalize_address_line(value: str, field: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise PydanticCustomError("missing", "{field} is required", {"field": field})
        return None
    cleaned = _clean(str(value))
    if not cleaned:
        if required:
            raise PydanticCustomError("missing", "{field} is required", {"field": field})
        return None
    if len(cleaned) > 200:
        raise PydanticCustomError(
            "invalid_address",
            "{field} must be at most 200 characters",
            {"field": field},
        )
    return cleaned


def normalize_insurance_provider(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean(str(value))
    if not cleaned:
        return None
    if len(cleaned) > 100:
        raise PydanticCustomError(
            "invalid_insurance_provider",
            "insurance_provider must be at most 100 characters",
            {},
        )
    return cleaned


def normalize_member_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean(str(value))
    if not cleaned:
        return None
    if not _MEMBER_ID_RE.match(cleaned):
        raise PydanticCustomError(
            "invalid_member_id",
            "insurance_member_id must be 1–50 alphanumeric characters",
            {},
        )
    return cleaned


def normalize_language(value: str | None) -> str:
    if value is None:
        return "English"
    cleaned = _clean(str(value))
    if not cleaned:
        return "English"
    if not _LANGUAGE_RE.match(cleaned) or len(cleaned) > 50:
        raise PydanticCustomError(
            "invalid_language",
            "preferred_language must be 1–50 letters, spaces, or hyphens",
            {},
        )
    return cleaned
