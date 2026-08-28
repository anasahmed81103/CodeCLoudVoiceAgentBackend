"""Pydantic request/response schemas. All writes are validated here, not only in the voice agent."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_serializer, field_validator

from app.validation import (
    format_date_of_birth,
    normalize_address_line,
    normalize_city,
    normalize_insurance_provider,
    normalize_language,
    normalize_member_id,
    normalize_person_name,
    normalize_sex,
    normalize_state,
    normalize_us_phone,
    normalize_zip_code,
    parse_date_of_birth,
)


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[EmailStr] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, value: str) -> str:
        return normalize_person_name(value, "first_name")

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, value: str) -> str:
        return normalize_person_name(value, "last_name")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, value: Any) -> date:
        return parse_date_of_birth(value)

    @field_validator("sex")
    @classmethod
    def _sex(cls, value: str) -> str:
        return normalize_sex(value).value

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_us_phone(value, "phone_number")

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("address_line_1")
    @classmethod
    def _address1(cls, value: str) -> str:
        return normalize_address_line(value, "address_line_1", required=True)  # type: ignore[return-value]

    @field_validator("address_line_2", mode="before")
    @classmethod
    def _address2(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_address_line(value, "address_line_2", required=False)

    @field_validator("city")
    @classmethod
    def _city(cls, value: str) -> str:
        return normalize_city(value)

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        return normalize_state(value)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, value: str) -> str:
        return normalize_zip_code(value)

    @field_validator("insurance_provider", mode="before")
    @classmethod
    def _insurer(cls, value: Any) -> str | None:
        return normalize_insurance_provider(_blank_to_none(value))

    @field_validator("insurance_member_id", mode="before")
    @classmethod
    def _member_id(cls, value: Any) -> str | None:
        return normalize_member_id(_blank_to_none(value))

    @field_validator("preferred_language", mode="before")
    @classmethod
    def _language(cls, value: Any) -> str:
        return normalize_language(_blank_to_none(value))

    @field_validator("emergency_contact_name", mode="before")
    @classmethod
    def _ec_name(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_person_name(value, "emergency_contact_name", max_len=100)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def _ec_phone(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_us_phone(value, "emergency_contact_phone")


class PatientUpdate(BaseModel):
    """Partial update. Omitted fields are left unchanged; explicit null clears optional fields."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_person_name(value, "first_name")

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_person_name(value, "last_name")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, value: Any) -> date | None:
        if value is None:
            return None
        return parse_date_of_birth(value)

    @field_validator("sex")
    @classmethod
    def _sex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_sex(value).value

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_us_phone(value, "phone_number")

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("address_line_1")
    @classmethod
    def _address1(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_address_line(value, "address_line_1", required=True)

    @field_validator("address_line_2", mode="before")
    @classmethod
    def _address2(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_address_line(value, "address_line_2", required=False)

    @field_validator("city")
    @classmethod
    def _city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_city(value)

    @field_validator("state")
    @classmethod
    def _state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_state(value)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_zip_code(value)

    @field_validator("insurance_provider", mode="before")
    @classmethod
    def _insurer(cls, value: Any) -> str | None:
        return normalize_insurance_provider(_blank_to_none(value))

    @field_validator("insurance_member_id", mode="before")
    @classmethod
    def _member_id(cls, value: Any) -> str | None:
        return normalize_member_id(_blank_to_none(value))

    @field_validator("preferred_language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        if value is None:
            return "English"
        return normalize_language(value)

    @field_validator("emergency_contact_name", mode="before")
    @classmethod
    def _ec_name(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_person_name(value, "emergency_contact_name", max_len=100)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def _ec_phone(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        return normalize_us_phone(value, "emergency_contact_phone")


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    @field_serializer("date_of_birth")
    def _ser_dob(self, value: date) -> str:
        return format_date_of_birth(value)

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _ser_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ErrorBody(BaseModel):
    message: str
    details: Optional[list[dict[str, Any]]] = None


class APIResponse(BaseModel):
    data: Any = None
    error: Optional[ErrorBody] = None
