"""Patient REST routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import APIResponse, PatientCreate, PatientUpdate
from app.services import patients as patient_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=APIResponse)
def list_patients(
    last_name: str | None = Query(default=None),
    date_of_birth: str | None = Query(default=None),
    phone_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    records = patient_service.list_patients(
        db,
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    return {"data": [patient_service.serialize(p) for p in records], "error": None}


@router.get("/{patient_id}", response_model=APIResponse)
def get_patient(patient_id: UUID, db: Session = Depends(get_db)):
    patient = patient_service.get_patient(db, patient_id)
    return {"data": patient_service.serialize(patient), "error": None}


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    patient = patient_service.create_patient(db, payload)
    return {"data": patient_service.serialize(patient), "error": None}


@router.put("/{patient_id}", response_model=APIResponse)
def update_patient(patient_id: UUID, payload: PatientUpdate, db: Session = Depends(get_db)):
    patient = patient_service.update_patient(db, patient_id, payload)
    return {"data": patient_service.serialize(patient), "error": None}


@router.delete("/{patient_id}", response_model=APIResponse)
def delete_patient(patient_id: UUID, db: Session = Depends(get_db)):
    patient = patient_service.soft_delete_patient(db, patient_id)
    return {"data": patient_service.serialize(patient), "error": None}
