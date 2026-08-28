"""Optional seed records so reviewers can query the API immediately after startup."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient

logger = logging.getLogger("carecloud.seed")

JANE_DOE_ID = "11111111-1111-4111-8111-111111111111"
CARLOS_OBRIEN_ID = "22222222-2222-4222-8222-222222222222"

SEED_PATIENTS = [
    Patient(
        patient_id=JANE_DOE_ID,
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1988, 4, 12),
        sex="Female",
        phone_number="4155552671",
        email="jane.doe@example.com",
        address_line_1="123 Market Street",
        address_line_2="Apt 4B",
        city="San Francisco",
        state="CA",
        zip_code="94105",
        insurance_provider="Blue Cross Blue Shield",
        insurance_member_id="XYZ123456",
        preferred_language="English",
        emergency_contact_name="John Doe",
        emergency_contact_phone="4155552672",
        created_at=datetime(2026, 1, 15, 16, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 15, 16, 30, tzinfo=timezone.utc),
    ),
    Patient(
        patient_id=CARLOS_OBRIEN_ID,
        first_name="Carlos",
        last_name="O'Brien",
        date_of_birth=date(1975, 11, 3),
        sex="Male",
        phone_number="2125550199",
        email=None,
        address_line_1="500 5th Avenue",
        address_line_2=None,
        city="New York",
        state="NY",
        zip_code="10110-1234",
        insurance_provider=None,
        insurance_member_id=None,
        preferred_language="Spanish",
        emergency_contact_name=None,
        emergency_contact_phone=None,
        created_at=datetime(2026, 2, 1, 14, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, 14, 0, tzinfo=timezone.utc),
    ),
]


def seed_if_empty(db: Session) -> None:
    existing = db.scalar(select(Patient.patient_id).limit(1))
    if existing is not None:
        return
    db.add_all(SEED_PATIENTS)
    db.commit()
    logger.info("seeded %s demo patient records", len(SEED_PATIENTS))
