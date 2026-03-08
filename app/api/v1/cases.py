"""CRUD endpoints for the Cases table."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.case import Case
from app.schemas.case import (
    CaseCreate,
    CaseDetailResponse,
    CaseResponse,
    CaseUpdate,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/cases", tags=["cases"])


# ── List / Filter ────────────────────────────────────────────────────
@router.get("", response_model=PaginatedResponse[CaseResponse])
def list_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    status: Optional[str] = None,
    jurisdiction_type: Optional[str] = None,
    area_of_application: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List cases with optional filters and full-text search."""
    stmt = select(Case)

    if status:
        stmt = stmt.where(Case.status_disposition.ilike(f"%{status}%"))
    if jurisdiction_type:
        stmt = stmt.where(Case.jurisdiction_type.ilike(f"%{jurisdiction_type}%"))
    if area_of_application:
        stmt = stmt.where(Case.area_of_application.ilike(f"%{area_of_application}%"))
    if q:
        stmt = stmt.where(
            Case.search_vector.op("@@")(func.to_tsquery("english", q))
        )

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    # Paginated results
    stmt = stmt.order_by(Case.date_action_filed.desc().nullslast()).offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()

    return PaginatedResponse(items=rows, total=total, skip=skip, limit=limit)


# ── Get by ID ────────────────────────────────────────────────────────
@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: int, db: Session = Depends(get_db)):
    """Get a single case with nested dockets, documents, and secondary sources."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


# ── Get by Record Number ─────────────────────────────────────────────
@router.get("/record/{record_number}", response_model=CaseDetailResponse)
def get_case_by_record_number(
    record_number: int, db: Session = Depends(get_db),
):
    """Look up a case by its Caspio record_number."""
    stmt = select(Case).where(Case.record_number == record_number)
    case = db.execute(stmt).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    return case


# ── Create ───────────────────────────────────────────────────────────
@router.post("", response_model=CaseResponse, status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)):
    """Create a new case."""
    case = Case(**payload.model_dump())
    db.add(case)
    db.flush()
    db.refresh(case)
    return case


# ── Update ───────────────────────────────────────────────────────────
@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: int, payload: CaseUpdate, db: Session = Depends(get_db),
):
    """Partially update a case."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    db.flush()
    db.refresh(case)
    return case


# ── Delete ───────────────────────────────────────────────────────────
@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: int, db: Session = Depends(get_db)):
    """Delete a case and all related records (cascade)."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    db.delete(case)
