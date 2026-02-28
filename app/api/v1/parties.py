"""
Parties API — CRUD endpoints for litigation parties.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import PaginationDep, require_api_key
from app.models.party import Party, CaseParty
from app.schemas.party import (
    PartyCreate,
    PartyUpdate,
    PartyResponse,
    CasePartyCreate,
    CasePartyResponse,
)
from app.schemas.common import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[PartyResponse])
async def list_parties(
    pagination: PaginationDep = Depends(),
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None, description="Search party name"),
    party_type: Optional[str] = Query(None),
):
    """List all parties with optional filtering."""
    query = select(Party).where(Party.is_alias == False)  # noqa: E712

    if search:
        query = query.where(Party.name.ilike(f"%{search}%"))
    if party_type:
        query = query.where(Party.party_type == party_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Party.name).offset(pagination.offset).limit(pagination.page_size)
    result = await db.execute(query)
    parties = result.scalars().all()

    return PaginatedResponse.create(
        items=[PartyResponse.model_validate(p) for p in parties],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{party_id}", response_model=PartyResponse)
async def get_party(party_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single party by ID."""
    result = await db.execute(select(Party).where(Party.id == party_id))
    party = result.scalar_one_or_none()
    if not party:
        raise HTTPException(status_code=404, detail=f"Party {party_id} not found")
    return PartyResponse.model_validate(party)


@router.post("", response_model=PartyResponse, status_code=201)
async def create_party(
    party_in: PartyCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Create a new party. Requires API key."""
    party = Party(**party_in.model_dump())
    db.add(party)
    await db.flush()
    await db.refresh(party)
    return PartyResponse.model_validate(party)


@router.patch("/{party_id}", response_model=PartyResponse)
async def update_party(
    party_id: int,
    party_in: PartyUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Update a party. Requires API key."""
    result = await db.execute(select(Party).where(Party.id == party_id))
    party = result.scalar_one_or_none()
    if not party:
        raise HTTPException(status_code=404, detail=f"Party {party_id} not found")

    for field, value in party_in.model_dump(exclude_unset=True).items():
        setattr(party, field, value)

    await db.flush()
    await db.refresh(party)
    return PartyResponse.model_validate(party)


@router.post("/case-party", response_model=CasePartyResponse, status_code=201)
async def add_party_to_case(
    cp_in: CasePartyCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Link a party to a case with a specific role."""
    case_party = CaseParty(**cp_in.model_dump())
    db.add(case_party)
    await db.flush()
    await db.refresh(case_party)
    return CasePartyResponse.model_validate(case_party)
