"""
Docket model — represents a court docket entry linked to a DAIL case.

Stores docket numbers, filing metadata, and links to CourtListener/PACER.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Docket(Base):
    __tablename__ = "dockets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Foreign Keys ─────────────────────────────────────────────────
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    court_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("courts.id", ondelete="SET NULL"), index=True
    )

    # ── Docket Identifiers ───────────────────────────────────────────
    docket_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    court_name: Mapped[Optional[str]] = mapped_column(String(500))

    # ── CourtListener Integration ────────────────────────────────────
    courtlistener_docket_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, index=True
    )
    courtlistener_url: Mapped[Optional[str]] = mapped_column(Text)
    pacer_case_id: Mapped[Optional[str]] = mapped_column(String(50))

    # ── Filing Metadata ──────────────────────────────────────────────
    date_filed: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_terminated: Mapped[Optional[date]] = mapped_column(Date)
    nature_of_suit: Mapped[Optional[str]] = mapped_column(String(500))

    # ── Party Info (denormalized summary) ────────────────────────────
    plaintiff_summary: Mapped[Optional[str]] = mapped_column(Text)
    defendant_summary: Mapped[Optional[str]] = mapped_column(Text)

    # ── Link ─────────────────────────────────────────────────────────
    link: Mapped[Optional[str]] = mapped_column(Text)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    case: Mapped["Case"] = relationship(back_populates="dockets")  # type: ignore[name-defined]
    court: Mapped[Optional["Court"]] = relationship(back_populates="dockets")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Docket(id={self.id}, number='{self.docket_number}')>"
