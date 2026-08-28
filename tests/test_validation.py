"""Unit tests for demographic field validation."""

from datetime import date, timedelta

import pytest
from pydantic_core import PydanticCustomError

from app.validation import (
    normalize_person_name,
    normalize_sex,
    normalize_state,
    normalize_us_phone,
    normalize_zip_code,
    parse_date_of_birth,
)


def test_names_accept_letters_hyphens_apostrophes():
    assert normalize_person_name("O'Brien", "last_name") == "O'Brien"
    assert normalize_person_name("Mary-Anne", "first_name") == "Mary-Anne"
    assert normalize_person_name("Ann Marie", "first_name") == "Ann Marie"


@pytest.mark.parametrize("value", ["", "A1", "John$", "Hyphen-", "'Start"])
def test_names_reject_invalid(value):
    with pytest.raises(PydanticCustomError):
        normalize_person_name(value, "first_name")


def test_dob_rejects_future_and_non_us_format():
    with pytest.raises(PydanticCustomError):
        parse_date_of_birth((date.today() + timedelta(days=1)).strftime("%m/%d/%Y"))
    with pytest.raises(PydanticCustomError):
        parse_date_of_birth("1990-04-12")
    with pytest.raises(PydanticCustomError):
        parse_date_of_birth("02/30/1990")
    assert parse_date_of_birth("04/12/1988") == date(1988, 4, 12)


def test_phone_normalizes_common_formats():
    assert normalize_us_phone("(415) 555-2671") == "4155552671"
    assert normalize_us_phone("+1 415-555-2671") == "4155552671"
    assert normalize_us_phone("4155552671") == "4155552671"


@pytest.mark.parametrize("value", ["123", "415555267", "0155552671", "4151552671"])
def test_phone_rejects_invalid(value):
    with pytest.raises(PydanticCustomError):
        normalize_us_phone(value)


def test_state_and_zip():
    assert normalize_state("ca") == "CA"
    with pytest.raises(PydanticCustomError):
        normalize_state("XX")
    assert normalize_zip_code("94105") == "94105"
    assert normalize_zip_code("94105-1234") == "94105-1234"
    with pytest.raises(PydanticCustomError):
        normalize_zip_code("9410")


def test_sex_aliases():
    assert normalize_sex("m").value == "Male"
    assert normalize_sex("decline to answer").value == "Decline to Answer"
    with pytest.raises(PydanticCustomError):
        normalize_sex("unknown")
