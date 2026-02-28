"""
Dockets API — CRUD endpoints for case dockets.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import require_api_key
from app.models.docket import Docket
from app.schemas.docket import DocketCreate, DocketUpdate, DocketResponse

router = APIRouter()


@router.get("/{docket_id}", response_model=DocketResponse)
async def get_docket(docket_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single docket by ID."""
    result = await db.execute(select(Docket).where(Docket.id == docket_id))
    docket = result.scalar_one_or_none()
    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_id} not found")
    return DocketResponse.model_validate(docket)


@router.post("", response_model=DocketResponse, status_code=201)
async def create_docket(
    docket_in: DocketCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Create a new docket. Requires API key."""
    docket = Docket(**docket_in.model_dump())
    db.add(docket)
    await db.flush()
    await db.refresh(docket)
    return DocketResponse.model_validate(docket)


@router.patch("/{docket_id}", response_model=DocketResponse)
async def update_docket(
    docket_id: int,
    docket_in: DocketUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Update a docket. Requires API key."""
    result = await db.execute(select(Docket).where(Docket.id == docket_id))
    docket = result.scalar_one_or_none()
    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_id} not found")

    for field, value in docket_in.model_dump(exclude_unset=True).items():
        setattr(docket, field, value)

    await db.flush()
    await db.refresh(docket)
    return DocketResponse.model_validate(docket)


@router.delete("/{docket_id}", status_code=204)
async def delete_docket(
    docket_id: int,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Delete a docket. Requires API key."""
    result = await db.execute(select(Docket).where(Docket.id == docket_id))
    docket = result.scalar_one_or_none()
    if not docket:
        raise HTTPException(status_code=404, detail=f"Docket {docket_id} not found")
    await db.delete(docket)
