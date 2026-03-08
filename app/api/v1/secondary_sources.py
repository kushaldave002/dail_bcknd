"""CRUD endpoints for the Secondary Sources table."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.secondary_source import SecondarySource
from app.schemas.common import PaginatedResponse
from app.schemas.secondary_source import (
    SecondarySourceCreate,
    SecondarySourceResponse,
    SecondarySourceUpdate,
)

router = APIRouter(prefix="/secondary-sources", tags=["secondary-sources"])


@router.get("", response_model=PaginatedResponse[SecondarySourceResponse])
def list_secondary_sources(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    case_number: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List secondary sources, optionally filtered by case_number."""
    stmt = select(SecondarySource)
    if case_number is not None:
        stmt = stmt.where(SecondarySource.case_number == case_number)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(SecondarySource.id).offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return PaginatedResponse(items=rows, total=total, skip=skip, limit=limit)


@router.get("/{source_id}", response_model=SecondarySourceResponse)
def get_secondary_source(source_id: int, db: Session = Depends(get_db)):
    src = db.get(SecondarySource, source_id)
    if not src:
        raise HTTPException(404, "Secondary source not found")
    return src


@router.post("", response_model=SecondarySourceResponse, status_code=201)
def create_secondary_source(
    payload: SecondarySourceCreate, db: Session = Depends(get_db),
):
    src = SecondarySource(**payload.model_dump())
    db.add(src)
    db.flush()
    db.refresh(src)
    return src


@router.patch("/{source_id}", response_model=SecondarySourceResponse)
def update_secondary_source(
    source_id: int,
    payload: SecondarySourceUpdate,
    db: Session = Depends(get_db),
):
    src = db.get(SecondarySource, source_id)
    if not src:
        raise HTTPException(404, "Secondary source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(src, field, value)
    db.flush()
    db.refresh(src)
    return src


@router.delete("/{source_id}", status_code=204)
def delete_secondary_source(
    source_id: int, db: Session = Depends(get_db),
):
    src = db.get(SecondarySource, source_id)
    if not src:
        raise HTTPException(404, "Secondary source not found")
    db.delete(src)
