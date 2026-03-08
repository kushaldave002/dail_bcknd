"""AI / LLM endpoints — GPT-4o-mini (OpenRouter) & Gemini integration."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.case import Case
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


# ── Request schemas ──────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        ..., min_length=1,
        description=(
            "Conversation history. Send a single message for a new conversation, "
            "or the full history for follow-ups. The system auto-detects intent."
        ),
    )


class NLQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural-language question about AI litigation")


class TrendRequest(BaseModel):
    question: str = Field(
        "What are the main trends in AI litigation?",
        description="Analytical question about DAIL data",
    )


class ClassifyRequest(BaseModel):
    caption: str
    brief_description: str | None = None
    summary_facts_activity: str | None = None
    organizations_involved: str | None = None


class ExtractDocumentRequest(BaseModel):
    image_url: str = Field(..., description="Public URL of the court-document image")
    mime_type: str = Field("image/png", description="MIME type (image/png, image/jpeg, etc.)")


# ── 0. Unified Chat — Intelligent Query Interface ────────────────────
@router.post("/chat")
async def ai_chat(body: ChatRequest, db: Session = Depends(get_db)):
    """Unified conversational endpoint with multi-turn support."""
    try:
        messages = [{"role": m.role, "content": m.content} for m in body.messages]
        return await ai_service.chat(messages, db)
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc


# ── 1. Natural-Language Search ───────────────────────────────────────
@router.post("/query")
async def ai_query(body: NLQueryRequest, db: Session = Depends(get_db)):
    """Convert a natural-language question into database filters via GPT."""
    try:
        return await ai_service.natural_language_search(body.query, db)
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc


# ── 2. Case Summarisation ───────────────────────────────────────────
@router.post("/summarize/{case_id}")
async def ai_summarize(case_id: int, db: Session = Depends(get_db)):
    """Generate a GPT summary for a specific case."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    case_data = {
        col.name: getattr(case, col.name)
        for col in case.__table__.columns
        if col.name != "search_vector"
    }
    try:
        return await ai_service.summarize_case(case_data)
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc


# ── 3. Trend Analysis ───────────────────────────────────────────────
@router.post("/analyze")
async def ai_analyze(body: TrendRequest, db: Session = Depends(get_db)):
    """Analyse trends across the DAIL dataset using GPT."""
    try:
        return await ai_service.analyze_trends(body.question, db)
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc


# ── 4. Auto-Classification ──────────────────────────────────────────
@router.post("/classify")
async def ai_classify(body: ClassifyRequest):
    """Suggest classification field values (area, issues, etc.) for a case."""
    try:
        return await ai_service.classify_case(body.model_dump())
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc


# ── 5. Document Image Extraction (Gemini) ────────────────────────────
@router.post("/extract-document")
async def ai_extract_document(body: ExtractDocumentRequest):
    """Extract text and structured fields from a court-document image using Gemini."""
    try:
        return await ai_service.extract_document_from_image(
            body.image_url, body.mime_type,
        )
    except Exception as exc:
        raise HTTPException(502, f"AI service error: {exc}") from exc
