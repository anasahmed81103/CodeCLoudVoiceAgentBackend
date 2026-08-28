"""CareCloud patient registration API + SQLite store.

Voice/LLM comes later; that layer should POST/PUT here after the caller confirms.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, BeforeValidator, ValidationError, field_validator
from sqlalchemy import Column, Date, DateTime, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("carecloud")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./patients.db")
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
    # Swagger often sends all-digit values as JSON numbers, not strings.
    if isinstance(v, bool):
        raise ValueError(f"{field} must be a valid U.S. 10-digit phone number")
    if isinstance(v, float):
        v = str(int(v))
    elif isinstance(v, int):
        v = str(v)
    digits = re.sub(r"\D", "", str(v))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"{field} must be a valid U.S. 10-digit phone number")
    return digits


def _opt_phone(v, field="phone_number"):
    if v is None or v == "":
        return None
    return check_phone(v, field)


Phone = Annotated[str, BeforeValidator(lambda v: check_phone(v))]
OptPhone = Annotated[Optional[str], BeforeValidator(lambda v: _opt_phone(v))]
OptEmergencyPhone = Annotated[
    Optional[str],
    BeforeValidator(lambda v: _opt_phone(v, "emergency_contact_phone")),
]


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
        # Store MM/DD/YYYY in the schema so Swagger does not use a YYYY-MM-DD picker.
        if v is None:
            return None
        return check_dob(v).strftime("%m/%d/%Y")

    @field_validator("sex", check_fields=False)
    @classmethod
    def v_sex(cls, v):
        return None if v is None else check_sex(v)

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


class PatientIn(Rules):
    model_config = ConfigDict(json_schema_extra={"example": {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "05/14/1992",
        "sex": "Female",
        "phone_number": "5551234567",
        "email": "jane.doe@example.com",
        "address_line_1": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip_code": "10001",
        "insurance_provider": "Blue Cross",
        "insurance_member_id": "BC123456",
        "preferred_language": "English",
        "emergency_contact_name": "John Doe",
        "emergency_contact_phone": "5559876543",
    }})

    first_name: str
    last_name: str
    date_of_birth: str
    sex: str
    phone_number: Phone
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
    emergency_contact_phone: OptEmergencyPhone = None


class PatientUpdate(Rules):
    """Send only fields to change. Omitted fields stay as they are."""

    model_config = ConfigDict(json_schema_extra={"example": {"first_name": "Jean"}})

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    phone_number: OptPhone = None
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
    emergency_contact_phone: OptEmergencyPhone = None


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


@app.get("/health")
def health():
    return {"status": "ok"}


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


def _to_row(data: dict) -> dict:
    if "date_of_birth" in data and data["date_of_birth"] is not None:
        data["date_of_birth"] = check_dob(data["date_of_birth"])
    return data


def persist_new_patient(db: Session, payload: PatientIn) -> Patient:
    p = Patient(**_to_row(payload.model_dump()))
    db.add(p)
    db.commit()
    db.refresh(p)
    log.info("patient.created %s", as_dict(p))
    return p


def persist_update(db: Session, patient_id: str, payload: PatientUpdate) -> Patient:
    p = active(db, patient_id)
    for k, v in _to_row(payload.model_dump(exclude_unset=True)).items():
        setattr(p, k, v)
    p.updated_at = utcnow()
    db.commit()
    db.refresh(p)
    log.info("patient.updated %s", as_dict(p))
    return p


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    return (
        db.query(Patient)
        .filter(Patient.phone_number == check_phone(phone_number), Patient.deleted_at.is_(None))
        .first()
    )


def _validation_text(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(x) for x in err.get("loc", ()) if x != "body")
        msg = err.get("msg", "Invalid value").removeprefix("Value error, ")
        parts.append(f"{field}: {msg}" if field else msg)
    return "; ".join(parts) or "Validation failed"


def _tool_calls(message: dict) -> list[dict]:
    raw = message.get("toolCallList") or message.get("toolCalls") or []
    if not raw:
        for item in message.get("toolWithToolCallList") or []:
            tc = item.get("toolCall") or {}
            fn = tc.get("function") or {}
            raw.append({
                "id": tc.get("id"),
                "name": item.get("name") or fn.get("name"),
                "parameters": tc.get("parameters") or fn.get("parameters") or fn.get("arguments"),
            })
    out = []
    for call in raw:
        fn = call.get("function") or {}
        args = call.get("parameters") or call.get("arguments") or fn.get("arguments") or fn.get("parameters") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        out.append({
            "id": call.get("id"),
            "name": call.get("name") or fn.get("name"),
            "args": args if isinstance(args, dict) else {},
        })
    return out


def _vapi_authorized(authorization: str | None, x_vapi_secret: str | None) -> bool:
    if not VAPI_WEBHOOK_SECRET:
        return True
    token = ""
    if authorization:
        token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    elif x_vapi_secret:
        token = x_vapi_secret
    return hmac.compare_digest(token, VAPI_WEBHOOK_SECRET)


def run_vapi_tool(db: Session, name: str | None, args: dict) -> str:
    if name == "lookup_patient":
        found = find_by_phone(db, args.get("phone_number") or "")
        if not found:
            return "No existing patient with that phone number. Continue registration, then call register_patient after the caller confirms."
        return (
            f"Existing patient found: {found.first_name} {found.last_name}, "
            f"patient_id {found.patient_id}. Ask if they want to update that record "
            "instead of creating a new one."
        )

    if name == "register_patient":
        p = persist_new_patient(db, PatientIn(**args))
        return (
            f"Successfully registered {p.first_name} {p.last_name}. "
            f"patient_id {p.patient_id}. Tell them they are all set, then end the call."
        )

    if name == "update_patient":
        patient_id = args.get("patient_id")
        if not patient_id:
            raise ValueError("patient_id is required to update a record")
        payload = PatientUpdate(**{k: v for k, v in args.items() if k != "patient_id"})
        p = persist_update(db, str(patient_id), payload)
        return f"Updated {p.first_name} {p.last_name}. Tell them the record is saved, then end the call."

    raise ValueError(f"Unknown tool: {name}")


@app.post("/patients")
def create_patient(payload: PatientIn, db: Session = Depends(get_db)):
    p = persist_new_patient(db, payload)
    return ok(as_dict(p), 201)


@app.put("/patients/{patient_id}", summary="Update a patient (partial)")
def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
    p = persist_update(db, patient_id, payload)
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


@app.post("/vapi-webhook")
async def vapi_webhook(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_vapi_secret: str | None = Header(default=None, alias="X-Vapi-Secret"),
):
    """Vapi Server URL. Always 200 on tool-calls so the agent can speak errors."""
    if not _vapi_authorized(authorization, x_vapi_secret):
        raise HTTPException(401, "Unauthorized")

    body = await request.json()
    message = body.get("message") or {}
    msg_type = message.get("type")

    if msg_type == "end-of-call-report":
        artifact = message.get("artifact") or {}
        log.info(
            "vapi.call_ended reason=%s transcript=%s",
            message.get("endedReason"),
            artifact.get("transcript"),
        )
        return {"status": "ok"}

    if msg_type != "tool-calls":
        return {"status": "ignored"}

    results = []
    for call in _tool_calls(message):
        call_id = call["id"]
        try:
            text = run_vapi_tool(db, call["name"], call["args"])
            results.append({"toolCallId": call_id, "result": text})
        except ValidationError as exc:
            db.rollback()
            log.warning("vapi.validation %s", _validation_text(exc))
            results.append({"toolCallId": call_id, "error": _validation_text(exc)})
        except HTTPException as exc:
            db.rollback()
            results.append({"toolCallId": call_id, "error": str(exc.detail)})
        except Exception as exc:
            db.rollback()
            log.exception("vapi.tool_error")
            results.append({"toolCallId": call_id, "error": str(exc).replace("\n", " ")})
    return {"results": results}
