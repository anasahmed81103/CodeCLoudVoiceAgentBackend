"""CareCloud patient registration API + SQLite store.

Voice/LLM comes later; that layer should POST/PUT here after the caller confirms.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, Date, DateTime, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("carecloud")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./patients.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
SEX = {
    "male": "Male", "m": "Male", "man": "Male",
    "female": "Female", "f": "Female", "woman": "Female",
    "other": "Other",
    "decline to answer": "Decline to Answer", "decline": "Decline to Answer",
}
NAME_RE = re.compile(r"^[A-Za-z](?:[A-Za-z]|[ '\-](?=[A-Za-z])){0,49}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MEMBER_RE = re.compile(r"^[A-Za-z0-9]{1,50}$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(32), nullable=False)
    phone_number = Column(String(10), nullable=False)
    email = Column(String(254), nullable=True)
    address_line_1 = Column(String(200), nullable=False)
    address_line_2 = Column(String(200), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)
    insurance_provider = Column(String(100), nullable=True)
    insurance_member_id = Column(String(50), nullable=True)
    preferred_language = Column(String(50), nullable=False, default="English")
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow)
    deleted_at = Column(DateTime, nullable=True)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def blank(v):
    if v is None:
        return None
    v = " ".join(str(v).split())
    return v or None


def check_name(v, field="name", n=50):
    v = blank(v)
    if not v or len(v) > n or not NAME_RE.match(v):
        raise ValueError(f"{field} must be 1–{n} letters (hyphens/apostrophes/spaces ok)")
    return v


def check_dob(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        parsed = v
    else:
        try:
            parsed = datetime.strptime(str(v).strip(), "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError("date_of_birth must be a valid date in MM/DD/YYYY") from exc
    if parsed > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    return parsed


def check_sex(v):
    key = blank(v).lower()
    if key in SEX:
        return SEX[key]
    if blank(v) in SEX.values():
        return blank(v)
    raise ValueError("sex must be Male, Female, Other, or Decline to Answer")


def check_phone(v, field="phone_number"):
    digits = re.sub(r"\D", "", str(v))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        raise ValueError(f"{field} must be a valid U.S. 10-digit phone number")
    return digits


def check_state(v):
    code = blank(v).upper()
    if code not in US_STATES:
        raise ValueError("state must be a valid 2-letter U.S. state abbreviation")
    return code


def check_zip(v):
    v = blank(v)
    if not v or not ZIP_RE.match(v):
        raise ValueError("zip_code must be 12345 or 12345-6789")
    return v


def check_city(v):
    v = blank(v)
    if not v or len(v) > 100 or not re.match(r"^[A-Za-z][A-Za-z .'\-]*[A-Za-z.]$|^[A-Za-z]$", v):
        raise ValueError("city must be 1–100 characters")
    return v


def check_email(v):
    v = blank(v)
    if v and not EMAIL_RE.match(v):
        raise ValueError("email must be a valid email address")
    return v


def check_member_id(v):
    v = blank(v)
    if v and not MEMBER_RE.match(v):
        raise ValueError("insurance_member_id must be alphanumeric")
    return v


class Rules(BaseModel):
    """Shared create/update validators. None means 'leave unset' on PUT."""

    @field_validator("first_name", check_fields=False)
    @classmethod
    def v_fn(cls, v):
        return None if v is None else check_name(v, "first_name")

    @field_validator("last_name", check_fields=False)
    @classmethod
    def v_ln(cls, v):
        return None if v is None else check_name(v, "last_name")

    @field_validator("date_of_birth", mode="before", check_fields=False)
    @classmethod
    def v_dob(cls, v):
        return None if v is None else check_dob(v)

    @field_validator("sex", check_fields=False)
    @classmethod
    def v_sex(cls, v):
        return None if v is None else check_sex(v)

    @field_validator("phone_number", check_fields=False)
    @classmethod
    def v_phone(cls, v):
        return None if v is None else check_phone(v)

    @field_validator("email", check_fields=False)
    @classmethod
    def v_email(cls, v):
        return check_email(v)

    @field_validator("address_line_1", check_fields=False)
    @classmethod
    def v_a1(cls, v):
        if v is None:
            return None
        v = blank(v)
        if not v:
            raise ValueError("address_line_1 is required")
        return v[:200]

    @field_validator("address_line_2", check_fields=False)
    @classmethod
    def v_a2(cls, v):
        return blank(v)

    @field_validator("city", check_fields=False)
    @classmethod
    def v_city(cls, v):
        return None if v is None else check_city(v)

    @field_validator("state", check_fields=False)
    @classmethod
    def v_state(cls, v):
        return None if v is None else check_state(v)

    @field_validator("zip_code", check_fields=False)
    @classmethod
    def v_zip(cls, v):
        return None if v is None else check_zip(v)

    @field_validator("insurance_provider", check_fields=False)
    @classmethod
    def v_ins(cls, v):
        return blank(v)

    @field_validator("insurance_member_id", check_fields=False)
    @classmethod
    def v_mid(cls, v):
        return check_member_id(v)

    @field_validator("preferred_language", check_fields=False)
    @classmethod
    def v_lang(cls, v):
        return None if v is None else (blank(v) or "English")

    @field_validator("emergency_contact_name", check_fields=False)
    @classmethod
    def v_ecn(cls, v):
        return None if not blank(v) else check_name(v, "emergency_contact_name", 100)

    @field_validator("emergency_contact_phone", check_fields=False)
    @classmethod
    def v_ecp(cls, v):
        return None if not blank(v) else check_phone(v, "emergency_contact_phone")


class PatientIn(Rules):
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
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class PatientUpdate(Rules):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
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


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_dict(p: Patient) -> dict:
    return {
        "patient_id": p.patient_id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "date_of_birth": p.date_of_birth.strftime("%m/%d/%Y"),
        "sex": p.sex,
        "phone_number": p.phone_number,
        "email": p.email,
        "address_line_1": p.address_line_1,
        "address_line_2": p.address_line_2,
        "city": p.city,
        "state": p.state,
        "zip_code": p.zip_code,
        "insurance_provider": p.insurance_provider,
        "insurance_member_id": p.insurance_member_id,
        "preferred_language": p.preferred_language,
        "emergency_contact_name": p.emergency_contact_name,
        "emergency_contact_phone": p.emergency_contact_phone,
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
        "deleted_at": iso(p.deleted_at),
    }


def ok(data, status=200):
    return JSONResponse({"data": data, "error": None}, status_code=status)


def fail(status, message):
    return JSONResponse({"data": None, "error": message}, status_code=status)


def parse_uuid(patient_id: str) -> str:
    try:
        uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(422, "patient_id must be a UUID")
    return patient_id


def active(db: Session, patient_id: str) -> Patient:
    p = (
        db.query(Patient)
        .filter(Patient.patient_id == parse_uuid(patient_id), Patient.deleted_at.is_(None))
        .first()
    )
    if not p:
        raise HTTPException(404, "Patient not found")
    return p


def seed():
    db = SessionLocal()
    try:
        if db.query(Patient).first():
            return
        db.add(Patient(
            patient_id="11111111-1111-4111-8111-111111111111",
            first_name="Jane", last_name="Doe",
            date_of_birth=date(1988, 4, 12), sex="Female",
            phone_number="4155552671", email="jane.doe@example.com",
            address_line_1="123 Market Street", address_line_2="Apt 4B",
            city="San Francisco", state="CA", zip_code="94105",
            insurance_provider="Blue Cross Blue Shield", insurance_member_id="XYZ123456",
            preferred_language="English",
            emergency_contact_name="John Doe", emergency_contact_phone="4155552672",
        ))
        db.add(Patient(
            patient_id="22222222-2222-4222-8222-222222222222",
            first_name="Carlos", last_name="O'Brien",
            date_of_birth=date(1975, 11, 3), sex="Male",
            phone_number="2125550199",
            address_line_1="500 5th Avenue",
            city="New York", state="NY", zip_code="10110-1234",
            preferred_language="Spanish",
        ))
        db.commit()
        log.info("seeded 2 demo patients")
    finally:
        db.close()


seed()
app = FastAPI(title="CareCloud Patient Registration API")


@app.exception_handler(HTTPException)
async def http_error(_req, exc: HTTPException):
    return fail(exc.status_code, exc.detail if isinstance(exc.detail, str) else "Request failed")


@app.exception_handler(RequestValidationError)
async def validation_error(_req, exc: RequestValidationError):
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return fail(400, "Invalid JSON in request body")
    parts = []
    for e in errors:
        field = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path"))
        msg = e.get("msg", "Invalid value").removeprefix("Value error, ")
        parts.append(f"{field}: {msg}" if field else msg)
    return fail(422, "; ".join(parts) or "Request validation failed")


@app.exception_handler(Exception)
async def unhandled(_req, exc: Exception):
    log.exception("unhandled error")
    return fail(500, "An unexpected error occurred")


@app.get("/patients")
def list_patients(
    last_name: Optional[str] = Query(None),
    date_of_birth: Optional[str] = Query(None),
    phone_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Patient).filter(Patient.deleted_at.is_(None))
    try:
        if last_name and last_name.strip():
            q = q.filter(Patient.last_name.ilike(last_name.strip()))
        if date_of_birth and date_of_birth.strip():
            q = q.filter(Patient.date_of_birth == check_dob(date_of_birth))
        if phone_number and phone_number.strip():
            q = q.filter(Patient.phone_number == check_phone(phone_number))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ok([as_dict(p) for p in q.order_by(Patient.created_at.desc()).all()])


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    return ok(as_dict(active(db, patient_id)))


@app.post("/patients")
def create_patient(payload: PatientIn, db: Session = Depends(get_db)):
    p = Patient(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    log.info("patient.created %s", as_dict(p))
    return ok(as_dict(p), 201)


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
    p = active(db, patient_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = utcnow()
    db.commit()
    db.refresh(p)
    log.info("patient.updated %s", as_dict(p))
    return ok(as_dict(p))


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    p = active(db, patient_id)
    now = utcnow()
    p.deleted_at = now
    p.updated_at = now
    db.commit()
    db.refresh(p)
    log.info("patient.soft_deleted %s", as_dict(p))
    return ok(as_dict(p))
