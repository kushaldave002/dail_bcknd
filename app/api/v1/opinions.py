"""
Opinions API — CRUD endpoints for opinion clusters and individual opinions.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.api.deps import require_api_key
from app.models.opinion import OpinionCluster, Opinion
from app.schemas.opinion import (
    OpinionClusterCreate,
    OpinionClusterResponse,
    OpinionCreate,
    OpinionResponse,
)

router = APIRouter()


# ── Opinion Clusters ─────────────────────────────────────────────────────
@router.get("/clusters/{cluster_id}", response_model=OpinionClusterResponse)
async def get_opinion_cluster(cluster_id: int, db: AsyncSession = Depends(get_db)):
    """Get an opinion cluster with all its opinions."""
    result = await db.execute(
        select(OpinionCluster)
        .options(selectinload(OpinionCluster.opinions))
        .where(OpinionCluster.id == cluster_id)
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Opinion cluster {cluster_id} not found")
    return OpinionClusterResponse.model_validate(cluster)


@router.post("/clusters", response_model=OpinionClusterResponse, status_code=201)
async def create_opinion_cluster(
    cluster_in: OpinionClusterCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Create a new opinion cluster. Requires API key."""
    cluster = OpinionCluster(**cluster_in.model_dump())
    db.add(cluster)
    await db.flush()
    await db.refresh(cluster)
    return OpinionClusterResponse.model_validate(cluster)


# ── Individual Opinions ──────────────────────────────────────────────────
@router.get("/{opinion_id}", response_model=OpinionResponse)
async def get_opinion(opinion_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single opinion by ID."""
    result = await db.execute(select(Opinion).where(Opinion.id == opinion_id))
    opinion = result.scalar_one_or_none()
    if not opinion:
        raise HTTPException(status_code=404, detail=f"Opinion {opinion_id} not found")
    return OpinionResponse.model_validate(opinion)


@router.post("", response_model=OpinionResponse, status_code=201)
async def create_opinion(
    opinion_in: OpinionCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    """Create a new opinion within a cluster. Requires API key."""
    opinion = Opinion(**opinion_in.model_dump())
    db.add(opinion)
    await db.flush()
    await db.refresh(opinion)
    return OpinionResponse.model_validate(opinion)
