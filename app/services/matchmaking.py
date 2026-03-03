"""
3-Layer matchmaking engine
  Layer 1 — Deterministic SQL filter (via Supabase PostgREST)
  Layer 2 — Weighted scoring (Python)
  Layer 3 — AI personalization (OpenAI GPT-4o-mini)
"""
from __future__ import annotations
from supabase import AsyncClient

from app.db.queries import filter_programs, get_match_settings, upsert_match_cache
from app.models.university import MatchResultItem
from app.services.ai import generate_match_summaries


# ─── Layer 2: Scoring helpers ─────────────────────────────────────────────────

def normalize_ranking(rank: int | None, max_rank: int = 1500) -> float:
    """Rank #1 → 1.0, unranked → 0.0"""
    if rank is None or rank <= 0:
        return 0.0
    return max(0.0, 1.0 - (rank / max_rank))


def cost_efficiency_score(tuition: int, budget: int, has_scholarship: bool, max_scholarship_pct: int | None) -> float:
    """
    How much budget headroom does this program offer?
    Returns 0–1; scholarship bonus +0.15 (capped at 1.0).
    """
    if budget <= 0:
        return 0.0
    ratio = (budget - tuition) / budget
    score = max(0.0, min(1.0, ratio))
    if has_scholarship:
        bonus = 0.15 * ((max_scholarship_pct or 25) / 100)
        score = min(1.0, score + bonus)
    return score


def _score_program(row: dict, budget: int, weights: dict) -> tuple[float, dict]:
    """
    Compute a weighted composite score for a single program row
    (which contains the joined university fields).
    Returns (total_score, breakdown_dict).
    """
    uni = row.get("universities") or {}

    ranking_score = normalize_ranking(uni.get("ranking_qs"))
    tuition = row.get("tuition_usd_per_year") or uni.get("tuition_usd_per_year") or 0
    ce_score = cost_efficiency_score(
        tuition,
        budget,
        uni.get("scholarships_available", False),
        uni.get("max_scholarship_pct"),
    )
    bd_acc = (uni.get("acceptance_rate_bd") or 50.0) / 100.0  # default 50% if unknown

    total = (
        ranking_score * weights["weight_ranking"]
        + ce_score    * weights["weight_cost_efficiency"]
        + bd_acc      * weights["weight_bd_acceptance"]
    )
    breakdown = {
        "ranking":        round(ranking_score, 4),
        "cost_efficiency": round(ce_score, 4),
        "bd_acceptance":  round(bd_acc, 4),
    }
    return round(total, 4), breakdown


# ─── Main engine ──────────────────────────────────────────────────────────────

async def run_matchmaking(
    client: AsyncClient,
    student: dict,
    run_ai: bool = True,
) -> list[MatchResultItem]:
    """
    Full 3-layer matchmaking for a student profile dict.
    Caches results in match_cache table.
    """
    settings = await get_match_settings(client)

    academic: dict = student.get("academic_history") or {}
    scores: dict   = student.get("test_scores") or {}

    # Layer 1 — filter
    candidates = await filter_programs(
        client=client,
        budget_usd=student["budget_usd_per_year"],
        countries=student.get("preferred_countries") or [],
        degree_level=student.get("preferred_degree") or "master",
        ielts=scores.get("ielts"),
        gpa_pct=academic.get("gpa_percentage"),
        fields=student.get("preferred_fields") or None,
        budget_buffer=float(settings.get("filter_budget_buffer", 0.10)),
    )

    if not candidates:
        return []

    # Layer 2 — score + sort
    scored: list[tuple[float, dict, dict]] = []
    for row in candidates:
        score, breakdown = _score_program(row, student["budget_usd_per_year"], settings)
        scored.append((score, breakdown, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_n = scored[:15]

    results: list[MatchResultItem] = []
    for score, breakdown, row in top_n:
        uni = row.get("universities") or {}
        results.append(
            MatchResultItem(
                university_id=uni.get("id", ""),
                program_id=row["id"],
                university_name=uni.get("name", ""),
                program_name=row["name"],
                country=uni.get("country", ""),
                tuition_usd_per_year=row.get("tuition_usd_per_year") or uni.get("tuition_usd_per_year"),
                ranking_qs=uni.get("ranking_qs"),
                score=score,
                breakdown=breakdown,
                ai_summary=None,
            )
        )

    # Layer 3 — AI summaries for top ai_top_n
    ai_n = int(settings.get("ai_top_n", 10))
    if run_ai and results:
        summaries = await generate_match_summaries(student, results[:ai_n])
        for i, summary in enumerate(summaries):
            results[i].ai_summary = summary

    # Cache
    cache_payload = [r.model_dump() for r in results]
    await upsert_match_cache(client, student["id"], cache_payload)

    return results
