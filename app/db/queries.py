"""
Raw SQL helpers executed via the Supabase PostgREST client or direct psycopg2.
For complex matchmaking queries we build raw SQL rather than chaining ORM calls.
"""
from datetime import datetime, timezone
from typing import Any
from supabase import AsyncClient


async def get_match_settings(client: AsyncClient) -> dict:
    """Return the most recently updated match_settings row."""
    res = await (
        client.table("match_settings")
        .select("*")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return {
            "weight_ranking": 0.30,
            "weight_cost_efficiency": 0.40,
            "weight_bd_acceptance": 0.30,
            "ai_top_n": 10,
            "filter_budget_buffer": 0.10,
        }
    return res.data[0]


async def filter_programs(
    client: AsyncClient,
    budget_usd: int,
    countries: list[str],
    degree_level: str,
    ielts: float | None,
    gpa_pct: int | None,
    fields: list[str] | None,
    budget_buffer: float = 0.10,
) -> list[dict]:
    """
    Layer-1 deterministic filter.
    Returns matching programs with joined university data.
    """
    max_budget = int(budget_usd * (1 + budget_buffer))

    query = (
        client.table("programs")
        .select(
            "*, universities!inner(id, name, country, city, ranking_qs, ranking_the, "
            "tuition_usd_per_year, acceptance_rate_overall, acceptance_rate_bd, "
            "scholarships_available, max_scholarship_pct, website)"
        )
        .eq("is_active", True)
        .lte("tuition_usd_per_year", max_budget)
        .eq("degree_level", degree_level)
        .in_("universities.country", countries)
    )

    if not countries:
        return []

    if fields:
        query = query.in_("field", fields)

    # IELTS / GPA JSONB filters applied in Python after fetch (PostgREST
    # does not support JSONB path filters via the REST API).
    res = await query.limit(200).execute()
    rows = res.data or []

    # Python-side JSONB requirement checks
    filtered = []
    for row in rows:
        reqs: dict = row.get("min_requirements") or {}
        min_ielts = reqs.get("ielts")
        min_gpa   = reqs.get("gpa_pct")
        if min_ielts and ielts is not None and ielts < min_ielts:
            continue
        if min_gpa and gpa_pct is not None and gpa_pct < min_gpa:
            continue
        filtered.append(row)

    return filtered


async def get_student_by_user_id(client: AsyncClient, user_id: str) -> dict | None:
    # maybe_single() returns None (not an exception) when no row is found
    res = await client.table("students").select("*").eq("user_id", user_id).maybe_single().execute()
    return res.data


async def get_application(client: AsyncClient, app_id: str) -> dict | None:
    res = await client.table("applications").select("*").eq("id", app_id).maybe_single().execute()
    return res.data


async def upsert_match_cache(
    client: AsyncClient, student_id: str, results: list[dict[str, Any]]
) -> None:
    await client.table("match_cache").upsert(
        {
            "student_id":    student_id,
            "match_results": results,
            "computed_at":   datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


async def get_match_cache(client: AsyncClient, student_id: str) -> dict | None:
    res = (
        await client.table("match_cache")
        .select("*")
        .eq("student_id", student_id)
        .maybe_single()
        .execute()
    )
    return res.data
