"""
OpenAI wrappers for:
  - Match personalization summaries (GPT-4o-mini)
  - University semantic embeddings (text-embedding-3-small)
"""
from __future__ import annotations
import json
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.models.university import MatchResultItem

_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().OPENAI_API_KEY)
    return _client


def _build_match_prompt(student: dict, matches: list[MatchResultItem]) -> str:
    academic = student.get("academic_history") or {}
    scores   = student.get("test_scores") or {}
    budget   = student.get("budget_usd_per_year", 0)

    uni_list = "\n".join(
        f"{i+1}. {m.university_name} — {m.program_name} ({m.country}) "
        f"| Tuition: ${m.tuition_usd_per_year:,}/yr | QS rank: {m.ranking_qs or 'N/A'} "
        f"| Score: {m.score:.2f}"
        for i, m in enumerate(matches)
    )

    return f"""You are an expert education counselor specializing in Bangladeshi students studying abroad.

Student profile:
- Academic: {json.dumps(academic)}
- Test scores: {json.dumps(scores)}
- Budget: ${budget:,}/year
- Preferred countries: {student.get("preferred_countries", [])}
- Preferred fields: {student.get("preferred_fields", [])}

Top matched universities:
{uni_list}

For each university listed above (in the same order), write EXACTLY one 2-sentence personalized fit summary
explaining why this specific university and program is a good match for THIS student.
Mention their specific strengths, budget fit, and any relevant factors.
Be direct and specific — no filler phrases like "This is a great choice".

Return ONLY a JSON array of strings (no markdown, no extra text):
["summary for #1", "summary for #2", ...]"""


async def generate_match_summaries(
    student: dict,
    matches: list[MatchResultItem],
) -> list[str]:
    """
    Generate personalized 2-sentence summaries for each match result.
    Returns a list of strings in the same order as `matches`.
    Falls back to empty strings if the API call fails.
    """
    if not matches:
        return []

    settings = get_settings()
    client = _get_openai()

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": _build_match_prompt(student, matches)}],
            temperature=0.4,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "[]"
        summaries: list[str] = json.loads(raw)
        # Pad or trim to match length
        while len(summaries) < len(matches):
            summaries.append("")
        return summaries[: len(matches)]
    except Exception as exc:
        print(f"[ai.py] generate_match_summaries failed: {exc}")
        return [""] * len(matches)


async def embed_text(text: str) -> list[float]:
    """
    Compute a 1536-dim embedding for semantic university search.
    Uses text-embedding-3-small (default output dims = 1536).
    """
    settings = get_settings()
    client = _get_openai()
    response = await client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


async def semantic_search_query(query: str) -> list[float]:
    """Embed a free-text search query for pgvector similarity search."""
    return await embed_text(query)
