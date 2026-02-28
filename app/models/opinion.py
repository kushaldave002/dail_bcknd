"""
Opinion models — OpinionCluster and Opinion.

Following CourtListener's pattern:
  Case → Docket → OpinionCluster → Opinion
An OpinionCluster groups opinions from a single hearing (majority, dissent, concurrence).
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    Date,
    DateTime,
    ForeignKey,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OpinionCluster(Base):
    """A group of opinions from a single hearing event."""
    __tablename__ = "opinion_clusters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    docket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dockets.id", ondelete="SET NULL"), index=True
    )

    # ── Identifiers ──────────────────────────────────────────────────
    courtlistener_cluster_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, index=True
    )

    # ── Cluster Metadata ─────────────────────────────────────────────
    case_name: Mapped[Optional[str]] = mapped_column(Text)
    date_filed: Mapped[Optional[date]] = mapped_column(Date, index=True)
    syllabus: Mapped[Optional[str]] = mapped_column(Text)
    procedural_history: Mapped[Optional[str]] = mapped_column(Text)
    judges: Mapped[Optional[str]] = mapped_column(Text)
    citation_count: Mapped[int] = mapped_column(Integer, server_default="0")

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    case: Mapped["Case"] = relationship(back_populates="opinion_clusters")  # type: ignore[name-defined]
    opinions: Mapped[list["Opinion"]] = relationship(
        back_populates="cluster", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<OpinionCluster(id={self.id}, case_name='{self.case_name}')>"


class Opinion(Base):
    """An individual opinion within a cluster (majority, dissent, etc.)."""
    __tablename__ = "opinions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("opinion_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Identifiers ──────────────────────────────────────────────────
    courtlistener_opinion_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, index=True
    )

    # ── Opinion Metadata ─────────────────────────────────────────────
    opinion_type: Mapped[Optional[str]] = mapped_column(String(50))
    author_str: Mapped[Optional[str]] = mapped_column(String(500))

    # ── Opinion Text ─────────────────────────────────────────────────
    plain_text: Mapped[Optional[str]] = mapped_column(Text)
    html: Mapped[Optional[str]] = mapped_column(Text)
    html_with_citations: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)

    # ── Full-Text Search ─────────────────────────────────────────────
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    cluster: Mapped["OpinionCluster"] = relationship(back_populates="opinions")

    __table_args__ = (
        Index("ix_opinions_search_vector", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Opinion(id={self.id}, type='{self.opinion_type}')>"
