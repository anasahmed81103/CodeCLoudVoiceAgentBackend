"""Patient persistence. Routers and (later) the voice agent both call this layer."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from pydantic_core import PydanticCustomError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions import APIError
from app.models import Patient
from app.schemas import PatientCreate, PatientOut, PatientUpdate
from app.validation import normalize_us_phone, parse_date_of_birth

logger = logging.getLogger("carecloud.patients")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize(patient: Patient) -> dict:
    return PatientOut.model_validate(patient).model_dump(mode="json")


def _active(stmt):
    return stmt.where(Patient.deleted_at.is_(None))


def _query_value(field: str, parser, value: str):
    try:
        return parser(value)
    except PydanticCustomError as exc:
        raise APIError(
            422,
            str(exc),
            details=[{"field": field, "message": str(exc)}],
        ) from exc


def list_patients(
    db: Session,
    *,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    stmt = _active(select(Patient).order_by(Patient.created_at.desc()))

    if last_name and last_name.strip():
        stmt = stmt.where(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth and date_of_birth.strip():
        dob = _query_value("date_of_birth", parse_date_of_birth, date_of_birth)
        stmt = stmt.where(Patient.date_of_birth == dob)
    if phone_number and phone_number.strip():
        phone = _query_value(
            "phone_number",
            lambda v: normalize_us_phone(v, "phone_number"),
            phone_number,
        )
        stmt = stmt.where(Patient.phone_number == phone)

    return list(db.scalars(stmt).all())


def get_patient(db: Session, patient_id: UUID) -> Patient:
    patient = db.get(Patient, str(patient_id))
    if patient is None or patient.deleted_at is not None:
        raise APIError(404, "Patient not found")
    return patient


def create_patient(db: Session, payload: PatientCreate) -> Patient:
    data = payload.model_dump()
    patient = Patient(**data)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    logger.info("patient.created %s", serialize(patient))
    return patient


def update_patient(db: Session, patient_id: UUID, payload: PatientUpdate) -> Patient:
    patient = get_patient(db, patient_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(patient, field, value)
    patient.updated_at = _utcnow()
    db.commit()
    db.refresh(patient)
    logger.info("patient.updated %s", serialize(patient))
    return patient


def soft_delete_patient(db: Session, patient_id: UUID) -> Patient:
    patient = get_patient(db, patient_id)
    now = _utcnow()
    patient.deleted_at = now
    patient.updated_at = now
    db.commit()
    db.refresh(patient)
    logger.info("patient.soft_deleted %s", serialize(patient))
    return patient


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    """Used later by the voice agent for returning-caller / duplicate detection."""
    normalized = normalize_us_phone(phone_number, "phone_number")
    stmt = _active(select(Patient).where(Patient.phone_number == normalized))
    return db.scalars(stmt).first()
