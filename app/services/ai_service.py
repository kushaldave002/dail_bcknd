"""
DAIL Backend - AI Service

LLM integration layer:
  • GPT-4o-mini (via OpenRouter) → intent routing, natural-language search,
                                   case summarisation, trend analysis,
                                   auto-classification
  • Gemini 3 Flash Preview (direct Google API) → court-document image
                                                  extraction
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional

import google.generativeai as genai
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── OpenRouter Client (for GPT-4o-mini) ──────────────────────────────
_openrouter_client: Optional[AsyncOpenAI] = None
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GPT_MODEL = "openai/gpt-4o-mini"


def _get_openrouter() -> AsyncOpenAI:
    """Singleton AsyncOpenAI client pointed at OpenRouter."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _openrouter_client


# ── Gemini Client (direct Google API) ────────────────────────────────
_gemini_configured = False
GEMINI_MODEL = "gemini-3-flash-preview"


def _ensure_gemini() -> None:
    global _gemini_configured
    if not _gemini_configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_configured = True


# ── Filterable case fields for GPT prompt context ────────────────────
FILTERABLE_FIELDS = [
    ("caption", "Case name / title"),
    ("area_of_application", "AI application area, e.g. 'Natural Language Processing', 'Computer Vision'"),
    ("issue_list", "Legal issues, e.g. 'Copyright', 'Privacy', 'Discrimination'"),
    ("cause_of_action_list", "Causes of action"),
    ("jurisdiction_type", "'U.S. Federal', 'U.S. State', 'International'"),
    ("status_disposition", "e.g. 'Active', 'Settled', 'Dismissed'"),
    ("organizations_involved", "Companies or organizations"),
    ("class_action_list", "Class-action status"),
    ("name_of_algorithm_list", "AI / algorithm names"),
    ("jurisdiction_name", "Specific jurisdiction"),
    ("researcher", "Researcher name"),
]

_FIELD_DESCRIPTION = "\n".join(
    f"  - {name}: {desc}" for name, desc in FILTERABLE_FIELDS
)


# =====================================================================
#  1. Natural-Language Search  (GPT-4o-mini via OpenRouter)
# =====================================================================
async def natural_language_search(
    query: str, db: Session
) -> dict[str, Any]:
    """Convert a plain-English question into SQL filters via GPT,
    execute the query, and return results with a GPT summary."""

    client = _get_openrouter()

    system_prompt = f"""You are a legal-database query assistant for the
Database of AI Litigation (DAIL).  Given a natural-language query, extract
structured search parameters.

Filterable columns in the *cases* table:
{_FIELD_DESCRIPTION}

Return **valid JSON** with exactly this shape:
{{
  "filters": {{ "column_name": "search_value", ... }},
  "keywords": ["word1", "word2"],
  "explanation": "Brief note on how you interpreted the query"
}}

Rules:
• Only include a filter when the query clearly implies it.
• Filter values will be matched with ILIKE %value%.
• keywords are extra free-text terms for full-text search.
• Do NOT invent column names outside the list above."""

    resp = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    parsed = json.loads(resp.choices[0].message.content)
    filters: dict = parsed.get("filters", {})
    keywords: list[str] = parsed.get("keywords", [])
    explanation: str = parsed.get("explanation", "")

    conditions: list[str] = []
    params: dict[str, Any] = {}
    valid_columns = {f[0] for f in FILTERABLE_FIELDS}

    for i, (col, val) in enumerate(filters.items()):
        if col not in valid_columns:
            continue
        param_key = f"p{i}"
        conditions.append(f"{col} ILIKE :{param_key}")
        params[param_key] = f"%{val}%"

    if keywords:
        ts_query = " | ".join(keywords)
        conditions.append("search_vector @@ to_tsquery('english', :ts)")
        params["ts"] = ts_query

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    sql = text(
        f"SELECT id, record_number, caption, area_of_application, "
        f"issue_list, status_disposition, jurisdiction_type, "
        f"organizations_involved, date_action_filed "
        f"FROM cases WHERE {where_clause} ORDER BY date_action_filed DESC NULLS LAST LIMIT 50"
    )
    rows = db.execute(sql, params).mappings().all()
    cases = [dict(r) for r in rows]

    if cases:
        summary_prompt = (
            f"The user asked: \"{query}\"\n\n"
            f"The database returned {len(cases)} case(s).  Here are the first "
            f"few:\n{json.dumps(cases[:10], default=str)}\n\n"
            "Write a concise 2-4 sentence summary of these results for a legal "
            "researcher.  Do not fabricate information."
        )
        summary_resp = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "You are a legal research assistant."},
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0.3,
        )
        summary = summary_resp.choices[0].message.content
    else:
        summary = "No cases matched the query."

    return {
        "query": query,
        "interpretation": explanation,
        "filters_applied": filters,
        "keywords": keywords,
        "total_results": len(cases),
        "cases": cases,
        "summary": summary,
    }


# =====================================================================
#  2. Case Summarisation  (GPT-4o-mini via OpenRouter)
# =====================================================================
async def summarize_case(case_data: dict[str, Any]) -> dict[str, Any]:
    """Generate a structured summary for a single case."""

    client = _get_openrouter()
    prompt = f"""Summarise this AI-litigation case for a legal researcher.

Case: {case_data.get('caption', 'N/A')}
Record #: {case_data.get('record_number', 'N/A')}
Status: {case_data.get('status_disposition', 'N/A')}
Area: {case_data.get('area_of_application', 'N/A')}
Issues: {case_data.get('issue_text', 'N/A')}
Causes of Action: {case_data.get('cause_of_action_text', 'N/A')}
Facts: {case_data.get('summary_facts_activity', 'N/A')}
Significance: {case_data.get('summary_of_significance', 'N/A')}
Organisations: {case_data.get('organizations_involved', 'N/A')}
Jurisdiction: {case_data.get('jurisdiction_name', 'N/A')} ({case_data.get('jurisdiction_type', 'N/A')})
Filed: {case_data.get('date_action_filed', 'N/A')}
Class Action: {case_data.get('class_action', 'N/A')}
Algorithm: {case_data.get('name_of_algorithm_text', 'N/A')}

Provide:
1. **Overview** (2-3 sentences)
2. **Key Legal Issues**
3. **AI Technology Involved**
4. **Current Status & Implications**
5. **Significance for AI Law**

Be concise and accurate.  Only use information provided above."""

    resp = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "You are a legal research assistant specialising in AI litigation."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return {
        "case_id": case_data.get("id"),
        "record_number": case_data.get("record_number"),
        "caption": case_data.get("caption"),
        "summary": resp.choices[0].message.content,
    }


# =====================================================================
#  3. Trend Analysis  (GPT-4o-mini via OpenRouter)
# =====================================================================
async def analyze_trends(
    question: str, db: Session
) -> dict[str, Any]:
    """Fetch aggregate data and ask GPT to identify trends."""

    client = _get_openrouter()

    stats_sql = text("""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE status_disposition ILIKE '%%active%%') AS active,
            count(*) FILTER (WHERE jurisdiction_type ILIKE '%%federal%%') AS federal,
            count(*) FILTER (WHERE jurisdiction_type ILIKE '%%state%%')   AS state,
            count(*) FILTER (WHERE class_action_list IS NOT NULL
                             AND class_action_list != '')               AS class_actions,
            min(date_action_filed) AS earliest_filing,
            max(date_action_filed) AS latest_filing
        FROM cases
    """)
    stats = dict(db.execute(stats_sql).mappings().first())

    area_sql = text("""
        SELECT area_of_application, count(*) AS cnt
        FROM cases
        WHERE area_of_application IS NOT NULL AND area_of_application != ''
        GROUP BY area_of_application ORDER BY cnt DESC LIMIT 15
    """)
    areas = [dict(r) for r in db.execute(area_sql).mappings().all()]

    issue_sql = text("""
        SELECT issue_list, count(*) AS cnt
        FROM cases
        WHERE issue_list IS NOT NULL AND issue_list != ''
        GROUP BY issue_list ORDER BY cnt DESC LIMIT 15
    """)
    issues = [dict(r) for r in db.execute(issue_sql).mappings().all()]

    year_sql = text("""
        SELECT EXTRACT(YEAR FROM date_action_filed)::int AS year, count(*) AS cnt
        FROM cases
        WHERE date_action_filed IS NOT NULL
        GROUP BY year ORDER BY year
    """)
    yearly = [dict(r) for r in db.execute(year_sql).mappings().all()]

    context_blob = json.dumps(
        {"stats": stats, "areas": areas, "issues": issues, "yearly": yearly},
        default=str,
    )
    prompt = (
        f"The user asked: \"{question}\"\n\n"
        f"Here is aggregated data from the DAIL database:\n{context_blob}\n\n"
        "Based on this data, provide an insightful analysis answering the "
        "user's question.  Include specific numbers.  Be concise (3-6 "
        "paragraphs)."
    )
    resp = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "You are a legal analytics expert specialising in AI litigation trends."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    return {
        "question": question,
        "analysis": resp.choices[0].message.content,
        "data": {
            "stats": stats,
            "top_areas": areas,
            "top_issues": issues,
            "yearly_filings": yearly,
        },
    }


# =====================================================================
#  4. Auto-Classification  (GPT-4o-mini via OpenRouter)
# =====================================================================
async def classify_case(case_data: dict[str, Any]) -> dict[str, Any]:
    """Given partial case data, suggest appropriate list-field values."""

    client = _get_openrouter()
    prompt = f"""You are a legal classifier for the Database of AI Litigation.
Given the case details below, suggest the best values for each classification
field.

Case: {case_data.get('caption', '')}
Description: {case_data.get('brief_description', '')}
Facts: {case_data.get('summary_facts_activity', '')}
Organisations: {case_data.get('organizations_involved', '')}

Return **valid JSON** with these keys (use null if uncertain):
{{
  "area_of_application": "suggested value",
  "issue_list": "suggested value",
  "cause_of_action_list": "suggested value",
  "name_of_algorithm_list": "suggested value",
  "class_action_list": "Yes / No / null",
  "jurisdiction_type": "U.S. Federal / U.S. State / International / null"
}}"""

    resp = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "You are a legal data classification assistant."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    suggestions = json.loads(resp.choices[0].message.content)
    return {"case_input": case_data, "suggestions": suggestions}


# =====================================================================
#  5. Document Image Extraction  (Gemini 3 Flash Preview — direct API)
# =====================================================================
async def extract_document_from_image(
    image_url: str,
    mime_type: str = "image/png",
) -> dict[str, Any]:
    """Use Google Gemini 3 Flash Preview to extract structured text
    from a court-document image (scan / screenshot)."""

    import httpx

    _ensure_gemini()
    model = genai.GenerativeModel(GEMINI_MODEL)

    async with httpx.AsyncClient(follow_redirects=True) as http:
        img_resp = await http.get(image_url, timeout=30)
        img_resp.raise_for_status()
        image_bytes = img_resp.content

    prompt = """Extract all text from the following court document image.
Then return valid JSON with these keys:
{
  "raw_text": "full extracted text",
  "case_name": "if identifiable",
  "court": "if identifiable",
  "date": "if identifiable (YYYY-MM-DD)",
  "docket_number": "if identifiable",
  "summary": "1-2 sentence summary of the document"
}
If a field is not identifiable, set it to null."""

    response = model.generate_content(
        [
            prompt,
            {"mime_type": mime_type, "data": image_bytes},
        ]
    )
    raw = response.text

    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        result = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        result = {"raw_text": raw, "parse_error": "Could not parse structured fields"}

    return result


# =====================================================================
#  6. Unified Chat — Multi-turn Intent Router with Schema Awareness
# =====================================================================

TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "case": {
        "endpoint": "POST /api/v1/cases",
        "auto_generated": ["record_number"],
        "required": ["caption"],
        "optional": [
            "case_slug", "brief_description", "area_of_application",
            "area_of_application_text", "issue_text", "issue_list",
            "cause_of_action_list", "cause_of_action_text",
            "name_of_algorithm_list", "name_of_algorithm_text",
            "class_action_list", "class_action", "organizations_involved",
            "jurisdiction_filed", "date_action_filed", "current_jurisdiction",
            "jurisdiction_type", "jurisdiction_type_text", "jurisdiction_name",
            "published_opinions", "published_opinions_binary",
            "status_disposition", "progress_notes", "researcher",
            "summary_of_significance", "summary_facts_activity",
            "most_recent_activity", "most_recent_activity_date", "keyword",
        ],
        "examples": {
            "caption": "Smith v. Tesla, Inc.",
            "brief_description": "A short summary of the case",
            "area_of_application": "'Autonomous Vehicles', 'Generative AI', 'Facial Recognition'",
            "issue_list": "'Copyright Infringement', 'Negligence', 'Privacy'",
            "cause_of_action_list": "'Negligence', 'Product Liability'",
            "organizations_involved": "Tesla, Inc.; OpenAI",
            "jurisdiction_filed": "N.D. Cal.",
            "date_action_filed": "2025-03-15 (YYYY-MM-DD)",
            "jurisdiction_type": "'U.S. Federal', 'U.S. State', 'International'",
            "jurisdiction_name": "California (federal)",
            "status_disposition": "'Active', 'Inactive', 'Settled', 'Dismissed'",
            "class_action_list": "'Yes' or 'No'",
            "name_of_algorithm_list": "'Autopilot', 'ChatGPT', 'DALL-E'",
            "researcher": "Your name",
        },
    },
    "docket": {
        "endpoint": "POST /api/v1/dockets",
        "auto_generated": [],
        "required": ["case_number"],
        "optional": ["court", "number", "link"],
        "examples": {
            "case_number": "132 (must match an existing case record_number)",
            "court": "Federal: N.D. Cal.",
            "number": "3:23-cv-05243",
            "link": "https://www.courtlistener.com/docket/...",
        },
    },
    "document": {
        "endpoint": "POST /api/v1/documents",
        "auto_generated": [],
        "required": ["case_number"],
        "optional": ["court", "date", "link", "cite_or_reference", "document"],
        "examples": {
            "case_number": "132 (must match an existing case record_number)",
            "court": "N.D. Cal.",
            "date": "2025-03-15 (YYYY-MM-DD)",
            "link": "https://www.courtlistener.com/...",
            "cite_or_reference": "Smith v. Tesla, No. 3:25-cv-01234 (N.D. Cal. filed Mar. 15, 2025)",
            "document": "Complaint",
        },
    },
    "secondary_source": {
        "endpoint": "POST /api/v1/secondary-sources",
        "auto_generated": [],
        "required": ["case_number"],
        "optional": ["secondary_source_link", "secondary_source_title"],
        "examples": {
            "case_number": "132 (must match an existing case record_number)",
            "secondary_source_link": "https://example.com/article",
            "secondary_source_title": "Article Title, Author Name, Publication",
        },
    },
}

INTENT_ROUTER_PROMPT = """You are an intent classifier for the Database of AI Litigation (DAIL).
Given the conversation, determine which action to take.

Available actions:
1. "search"              — Find cases matching criteria
2. "summarize"           — Summarize a specific case (user mentions a case ID, record number, or name)
3. "analyze"             — Analyze trends, statistics, or patterns across the dataset
4. "classify"            — Classify or suggest fields for a described case
5. "create_case"         — User wants to add/create/insert a new case
6. "create_docket"       — User wants to add a new docket entry
7. "create_document"     — User wants to add a new document entry
8. "create_secondary_source" — User wants to add a new secondary source
9. "general"             — General question, greeting, or doesn't fit above

Return **valid JSON** with this exact shape:
{
  "intent": "search | summarize | analyze | classify | create_case | create_docket | create_document | create_secondary_source | general",
  "parameters": {
    // For "search": { "query": "the search query" }
    // For "summarize": { "case_id": 123 } or { "case_name": "partial name" }
    // For "analyze": { "question": "the analytical question" }
    // For "classify": { "caption": "...", "brief_description": "..." }
    // For "create_*": extract ALL fields the user mentioned as key-value pairs
    // For "general": {}
  },
  "reasoning": "Brief explanation"
}

Rules:
• If the user asks to add, create, insert, or register a new case → "create_case"
• If the user asks to add a docket → "create_docket"
• If the user asks to add a document → "create_document"
• If the user asks to add a secondary source → "create_secondary_source"
• If the user asks to find, show, list, or search → "search"
• If the user asks to summarize or explain a specific case → "summarize"
• If the user asks about trends, statistics, growth → "analyze"
• If the user describes a hypothetical case and asks how to classify it → "classify"
• For create intents, extract every field value the user provided in the message.
  Look across ALL messages in the conversation to gather cumulative field values."""


def _build_field_extraction_prompt(table: str, asked_optional: bool) -> str:
    """Build a prompt that asks GPT to extract fields from the full conversation."""
    schema = TABLE_SCHEMAS[table]
    auto_fields = set(schema.get("auto_generated", []))
    all_fields = schema["required"] + schema["optional"]
    examples = schema["examples"]

    field_lines = []
    for f in all_fields:
        req = " (REQUIRED)" if f in schema["required"] else ""
        ex = f" — e.g. {examples[f]}" if f in examples else ""
        field_lines.append(f"  - {f}{req}{ex}")

    auto_note = ""
    if auto_fields:
        auto_note = (
            f"• The following fields are AUTO-GENERATED by the system and must "
            f"NOT appear in extracted, missing_required, or missing_recommended: "
            f"{', '.join(auto_fields)}\n"
        )

    opt_rule = (
        '• "missing_recommended" should list important optional fields NOT yet provided '
        "(pick the 3-5 most useful ones a researcher would want to fill in)."
        if not asked_optional
        else '• "missing_recommended" should be an empty list (optional fields were already asked).'
    )

    return f"""You are a data extraction assistant for the DAIL database.
Given the full conversation, extract all field values the user has provided
for creating a new **{table}** record.

Available fields (user-provided only):
{chr(10).join(field_lines)}

Return **valid JSON** with this exact shape:
{{
  "extracted": {{ "field_name": "value", ... }},
  "missing_required": ["field1", "field2"],
  "missing_recommended": ["field1", "field2"]
}}

Rules:
{auto_note}• "extracted" should contain every field the user mentioned with its value.
• "missing_required" should list required fields NOT yet provided by the user.
{opt_rule}
• Convert dates to YYYY-MM-DD format.
• Convert case_number to integers.
• Do NOT invent values — only extract what the user explicitly stated.
• If the user did NOT explicitly provide a value for a required field, it MUST appear in missing_required."""


def _has_assistant_asked_optional(messages: list[dict[str, str]]) -> bool:
    """Check if a previous assistant turn already asked for optional fields."""
    for m in messages:
        if m["role"] == "assistant" and "recommend" in m.get("content", "").lower():
            return True
    return False


def _coerce_record(table: str, data: dict[str, Any]) -> dict[str, Any]:
    """Coerce LLM-extracted string values to the types the ORM expects."""
    from datetime import date as date_type

    int_fields = {"record_number", "case_number"}
    date_fields = {"date_action_filed", "most_recent_activity_date", "date"}
    bool_fields = {"published_opinions_binary"}

    clean: dict[str, Any] = {}
    for k, v in data.items():
        if v is None or v == "":
            continue
        if k in int_fields:
            clean[k] = int(v) if not isinstance(v, int) else v
        elif k in date_fields:
            if isinstance(v, str):
                clean[k] = date_type.fromisoformat(v)
            else:
                clean[k] = v
        elif k in bool_fields:
            clean[k] = str(v).lower() in ("true", "1", "yes")
        else:
            clean[k] = v
    return clean


def _insert_record(table: str, data: dict[str, Any], db: Session) -> dict[str, Any]:
    """Coerce types, auto-generate keys, and insert a record."""
    from app.models.case import Case
    from app.models.docket import Docket
    from app.models.document import Document
    from app.models.secondary_source import SecondarySource

    model_map = {
        "case": Case,
        "docket": Docket,
        "document": Document,
        "secondary_source": SecondarySource,
    }

    # Auto-generate record_number for cases
    if table == "case" and "record_number" not in data:
        row = db.execute(
            text("SELECT COALESCE(MAX(record_number), 0) + 1 AS next_rn FROM cases")
        )
        data["record_number"] = row.scalar_one()

    model_cls = model_map[table]
    clean_data = _coerce_record(table, data)
    obj = model_cls(**clean_data)
    db.add(obj)
    db.flush()
    db.refresh(obj)

    return {
        col.name: getattr(obj, col.name)
        for col in obj.__table__.columns
        if col.name != "search_vector"
    }


async def chat(messages: list[dict[str, str]], db: Session) -> dict[str, Any]:
    """Multi-turn chat endpoint: classify intent from conversation history,
    dispatch to the right handler, and for create operations check the
    schema and ask follow-up questions for missing fields.  Once all
    required fields are present, auto-execute the insert."""

    from app.models.case import Case

    client = _get_openrouter()
    last_message = messages[-1]["content"]

    # Step 1 — Classify intent from full conversation
    intent_resp = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": INTENT_ROUTER_PROMPT},
            *messages,
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    routing = json.loads(intent_resp.choices[0].message.content)
    intent = routing.get("intent", "general")
    params = routing.get("parameters", {})
    reasoning = routing.get("reasoning", "")

    # Step 2 — Dispatch
    try:
        # ── Create operations (schema-aware with follow-up + auto-execute) ──
        if intent.startswith("create_"):
            table = intent.replace("create_", "")
            if table not in TABLE_SCHEMAS:
                table = "case"
            schema = TABLE_SCHEMAS[table]
            asked_optional = _has_assistant_asked_optional(messages)

            extraction_resp = await client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": _build_field_extraction_prompt(table, asked_optional)},
                    *messages,
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            extraction = json.loads(extraction_resp.choices[0].message.content)
            extracted = extraction.get("extracted", {})
            missing_required = extraction.get("missing_required", [])
            missing_recommended = extraction.get("missing_recommended", [])

            # ── Still missing required fields → always ask ────────────
            if missing_required:
                examples = schema["examples"]
                lines = []
                for f in missing_required:
                    ex = f" (e.g. {examples[f]})" if f in examples else ""
                    lines.append(f"  - **{f}**{ex}")

                provided_lines = []
                for k, v in extracted.items():
                    provided_lines.append(f"  - {k}: {v}")

                response_text = f"I'd love to help you add this {table} record! "
                if provided_lines:
                    response_text += "Here's what I have so far:\n\n"
                    response_text += "\n".join(provided_lines) + "\n\n"
                response_text += (
                    "I still need the following **required** fields:\n\n"
                    + "\n".join(lines) + "\n"
                )

                if not asked_optional and missing_recommended:
                    rec_lines = []
                    for f in missing_recommended[:5]:
                        ex = f" (e.g. {examples[f]})" if f in examples else ""
                        rec_lines.append(f"  - {f}{ex}")
                    response_text += (
                        "\nI'd also recommend these optional fields "
                        "for a more complete record:\n\n"
                        + "\n".join(rec_lines) + "\n"
                    )

                response_text += (
                    "\nPlease provide the required fields "
                    "(and any optional ones you'd like to include)."
                )

                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": response_text,
                    "data": {
                        "extracted_so_far": extracted,
                        "missing_required": missing_required,
                        "missing_recommended": missing_recommended,
                    },
                }

            # ── All required present — insert into database ───────────
            try:
                created = _insert_record(table, extracted, db)
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "created",
                    "response": (
                        f"Done! The {table} record has been successfully "
                        f"created in the database.\n\n"
                        f"```json\n{json.dumps(created, indent=2, default=str)}\n```"
                    ),
                    "data": {"record": created},
                }
            except Exception as insert_err:
                logger.exception("Insert failed for %s", table)
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "error",
                    "response": (
                        f"I had all the fields ready, but the insert failed: "
                        f"{insert_err}\n\nPlease check the values and try again."
                    ),
                    "data": {"record": extracted, "error": str(insert_err)},
                }

        # ── Read operations ────────────────────────────────────────────
        elif intent == "search":
            query = params.get("query", last_message)
            if not query or query.strip().lower() in ("search", "find", "show", "list"):
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": (
                        "I'd be happy to search the database for you! "
                        "Could you tell me what you're looking for? For example:\n\n"
                        "  - \"Show me cases involving facial recognition\"\n"
                        "  - \"Find cases filed in N.D. Cal.\"\n"
                        "  - \"List active cases about autonomous vehicles\""
                    ),
                    "data": None,
                }
            result = await natural_language_search(query, db)
            return {
                "intent": intent,
                "reasoning": reasoning,
                "status": "complete",
                "response": result["summary"],
                "data": result,
            }

        elif intent == "summarize":
            case_id = params.get("case_id")
            case_name = params.get("case_name")

            if not case_id and not case_name:
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": (
                        "I'd be happy to summarize a case for you! "
                        "Which case would you like me to summarize? "
                        "You can provide:\n\n"
                        "  - A **case name** (e.g. \"Smith v. Tesla\")\n"
                        "  - A **record number** (e.g. 132)\n\n"
                        "If you're not sure, try searching first with something like "
                        "\"Show me cases involving OpenAI\"."
                    ),
                    "data": None,
                }

            case_obj = None
            if case_id:
                case_obj = db.get(Case, int(case_id))
            if not case_obj and case_name:
                stmt = select(Case).where(
                    Case.caption.ilike(f"%{case_name}%")
                ).limit(1)
                row = db.execute(stmt)
                case_obj = row.scalar_one_or_none()

            if not case_obj:
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": (
                        "I couldn't find a case matching that. "
                        "Could you double-check the name or record number?\n\n"
                        "You can also try searching first — for example: "
                        "\"Show me cases involving OpenAI\"."
                    ),
                    "data": None,
                }

            case_data = {
                col.name: getattr(case_obj, col.name)
                for col in case_obj.__table__.columns
                if col.name != "search_vector"
            }
            result = await summarize_case(case_data)
            return {
                "intent": intent,
                "reasoning": reasoning,
                "status": "complete",
                "response": result["summary"],
                "data": result,
            }

        elif intent == "analyze":
            question = params.get("question", last_message)
            if not question or question.strip().lower() in ("analyze", "analyse", "trends", "statistics"):
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": (
                        "I can analyze trends in the AI litigation database! "
                        "What would you like to know? For example:\n\n"
                        "  - \"What are the main trends in AI litigation?\"\n"
                        "  - \"How has the number of filings changed over time?\"\n"
                        "  - \"Which areas of AI have the most lawsuits?\""
                    ),
                    "data": None,
                }
            result = await analyze_trends(question, db)
            return {
                "intent": intent,
                "reasoning": reasoning,
                "status": "complete",
                "response": result["analysis"],
                "data": result,
            }

        elif intent == "classify":
            caption = params.get("caption", "")
            brief_description = params.get("brief_description", "")

            if not caption and not brief_description:
                return {
                    "intent": intent,
                    "reasoning": reasoning,
                    "status": "needs_info",
                    "response": (
                        "I can help classify a case! Please provide at least:\n\n"
                        "  - **Case name / caption** (e.g. \"Doe v. Google LLC\")\n\n"
                        "For better results, also include:\n\n"
                        "  - A brief description of the case\n"
                        "  - Organizations involved\n"
                        "  - Key facts or activities"
                    ),
                    "data": None,
                }

            case_input = {
                "caption": caption or last_message,
                "brief_description": brief_description,
                "summary_facts_activity": params.get("summary_facts_activity", ""),
                "organizations_involved": params.get("organizations_involved", ""),
            }
            result = await classify_case(case_input)
            return {
                "intent": intent,
                "reasoning": reasoning,
                "status": "complete",
                "response": (
                    "Here are the suggested classifications:\n"
                    + json.dumps(result["suggestions"], indent=2)
                ),
                "data": result,
            }

        else:  # general
            general_resp = await client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": (
                        "You are the DAIL (Database of AI Litigation) research assistant. "
                        "You help legal researchers explore a database of 375+ AI litigation "
                        "cases. You can: search for cases, summarize specific cases, analyze "
                        "trends, classify new cases, and help add new records (cases, dockets, "
                        "documents, secondary sources). Be helpful and concise."
                    )},
                    *messages,
                ],
                temperature=0.5,
            )
            return {
                "intent": intent,
                "reasoning": reasoning,
                "status": "complete",
                "response": general_resp.choices[0].message.content,
                "data": None,
            }

    except Exception as exc:
        logger.exception("Chat dispatch error for intent=%s", intent)
        raise
