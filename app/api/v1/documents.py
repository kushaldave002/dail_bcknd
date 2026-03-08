"""CRUD endpoints for the Documents table."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.document import Document
from app.schemas.common import PaginatedResponse
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentUpdate

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=PaginatedResponse[DocumentResponse])
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    case_number: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List documents, optionally filtered by case_number."""
    stmt = select(Document)
    if case_number is not None:
        stmt = stmt.where(Document.case_number == case_number)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(Document.date.desc().nullslast()).offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return PaginatedResponse(items=rows, total=total, skip=skip, limit=limit)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("", response_model=DocumentResponse, status_code=201)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db)):
    doc = Document(**payload.model_dump())
    db.add(doc)
    db.flush()
    db.refresh(doc)
    return doc


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int, payload: DocumentUpdate, db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(doc, field, value)
    db.flush()
    db.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    db.delete(doc)
