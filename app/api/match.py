"""
POST /match           — run full 3-layer matchmaking for authenticated student
GET  /match/results   — return cached results (fast)
DELETE /match/cache   — invalidate cache (e.g., after profile update)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from supabase import AsyncClient

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.client import get_client
from app.db.queries import get_student_by_user_id, get_match_cache
from app.models.university import MatchResultItem
from app.services.matchmaking import run_matchmaking

router = APIRouter(prefix="/match", tags=["match"])


@router.post("", response_model=list[MatchResultItem])
@limiter.limit(get_settings().MATCH_RATE_LIMIT)
async def run_match(
    request: Request,
    run_ai: bool = True,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    """
    Run full matchmaking (filter → score → AI) for the authenticated student.
    Results are cached in match_cache; re-running overwrites the cache.
    """
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    results = await run_matchmaking(client, student, run_ai=run_ai)
    return results


@router.get("/results", response_model=list[MatchResultItem])
async def get_results(
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    """Return cached match results. Returns 404 if match has not been run yet."""
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    cache = await get_match_cache(client, student["id"])
    if not cache:
        raise HTTPException(status_code=404, detail="No match results yet. POST /match to run matching.")

    return cache["match_results"]


@router.delete("/cache", status_code=204)
async def invalidate_cache(
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    """Invalidate the match cache for the authenticated student."""
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    await client.table("match_cache").delete().eq("student_id", student["id"]).execute()
