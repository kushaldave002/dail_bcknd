"""CRUD endpoints for the Dockets table."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.docket import Docket
from app.schemas.common import PaginatedResponse
from app.schemas.docket import DocketCreate, DocketResponse, DocketUpdate

router = APIRouter(prefix="/dockets", tags=["dockets"])


@router.get("", response_model=PaginatedResponse[DocketResponse])
def list_dockets(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    case_number: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List dockets, optionally filtered by case_number."""
    stmt = select(Docket)
    if case_number is not None:
        stmt = stmt.where(Docket.case_number == case_number)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(Docket.id).offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return PaginatedResponse(items=rows, total=total, skip=skip, limit=limit)


@router.get("/{docket_id}", response_model=DocketResponse)
def get_docket(docket_id: int, db: Session = Depends(get_db)):
    docket = db.get(Docket, docket_id)
    if not docket:
        raise HTTPException(404, "Docket not found")
    return docket


@router.post("", response_model=DocketResponse, status_code=201)
def create_docket(payload: DocketCreate, db: Session = Depends(get_db)):
    docket = Docket(**payload.model_dump())
    db.add(docket)
    db.flush()
    db.refresh(docket)
    return docket


@router.patch("/{docket_id}", response_model=DocketResponse)
def update_docket(
    docket_id: int, payload: DocketUpdate, db: Session = Depends(get_db),
):
    docket = db.get(Docket, docket_id)
    if not docket:
        raise HTTPException(404, "Docket not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(docket, field, value)
    db.flush()
    db.refresh(docket)
    return docket


@router.delete("/{docket_id}", status_code=204)
def delete_docket(docket_id: int, db: Session = Depends(get_db)):
    docket = db.get(Docket, docket_id)
    if not docket:
        raise HTTPException(404, "Docket not found")
    db.delete(docket)
