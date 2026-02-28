"""
Citations API — endpoints for citation data and citation graph queries.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import PaginationDep, require_api_key
from app.models.citation import Citation
from app.schemas.citation import CitationCreate, CitationResponse
from app.schemas.common import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[CitationResponse])
async def list_citations(
    pagination: PaginationDep = Depends(),
    db: AsyncSession = Depends(get_db),
    citing_case_id: Optional[int] = Query(None, description="Filter by citing case"),
    cited_case_id: Optional[int] = Query(None, description="Filter by cited case"),
    citation_type: Optional[str] = Query(None, description="Filter by citation type"),
):
    """List citations with optional filtering."""
    query = select(Citation)

    if citing_case_id:
        query = query.where(Citation.citing_case_id == citing_case_id)
    if cited_case_id:
        query = query.where(Citation.cited_case_id == cited_case_id)
    if citation_type:
        query = query.where(Citation.citation_type == citation_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Citation.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    result = await db.execute(query)
    citations = result.scalars().all()

    return PaginatedResponse.create(
        items=[CitationResponse.model_validate(c) for c in citations],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{citation_id}", response_model=CitationResponse)
async def get_citation(citation_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single citation by ID."""
    result = await db.execute(select(Citation).where(Citation.id == citation_id))
    citation = result.scalar_one_or_none()
    if not citation:
        raise HTTPException(status_code=404, detail=f"Citation {citation_id} not found")
    return CitationResponse.model_validate(citation)


@router.post("", response_model=CitationResponse, status_code=201)
async def create_citation(
    citation_in: CitationCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Create a new citation. Requires API key."""
    citation = Citation(**citation_in.model_dump())
    db.add(citation)
    await db.flush()
    await db.refresh(citation)
    return CitationResponse.model_validate(citation)


@router.get("/case/{case_id}/citing", response_model=list[CitationResponse])
async def get_citations_by_case(case_id: int, db: AsyncSession = Depends(get_db)):
    """Get all citations where this case is the citing party."""
    result = await db.execute(
        select(Citation).where(Citation.citing_case_id == case_id)
    )
    return [CitationResponse.model_validate(c) for c in result.scalars().all()]


@router.get("/case/{case_id}/cited-by", response_model=list[CitationResponse])
async def get_cited_by_case(case_id: int, db: AsyncSession = Depends(get_db)):
    """Get all citations where this case is being cited."""
    result = await db.execute(
        select(Citation).where(Citation.cited_case_id == case_id)
    )
    return [CitationResponse.model_validate(c) for c in result.scalars().all()]
