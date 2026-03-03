"""
GET  /consultants              — directory sorted by agency rating
GET  /consultants/{id}         — consultant detail
GET  /agencies                 — agency directory
POST /agencies                 — create agency
POST /reviews                  — student submits agency review
GET  /agencies/{id}/reviews    — paginated reviews for an agency
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import AsyncClient

from app.core.security import get_current_user
from app.db.client import get_client
from app.db.queries import get_student_by_user_id
from app.models.application import ReviewCreate, ReviewOut, AgencyOut, ConsultantOut

router = APIRouter(tags=["consultants"])


# ─── Consultants ──────────────────────────────────────────────────────────────

@router.get("/consultants", response_model=list[dict])
async def list_consultants(
    agency_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: AsyncClient = Depends(get_client),
):
    offset = (page - 1) * page_size
    query = (
        client.table("consultants")
        .select("*, agencies(name, avg_rating, review_count)")
        .order("agencies.avg_rating", desc=True)
    )
    if agency_id:
        query = query.eq("agency_id", agency_id)

    res = await query.range(offset, offset + page_size - 1).execute()
    return res.data or []


@router.get("/consultants/{consultant_id}", response_model=dict)
async def get_consultant(
    consultant_id: str,
    client: AsyncClient = Depends(get_client),
):
    res = await (
        client.table("consultants")
        .select("*, agencies(*)")
        .eq("id", consultant_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Consultant not found")
    return res.data


# ─── Agencies ─────────────────────────────────────────────────────────────────

@router.get("/agencies", response_model=list[AgencyOut])
async def list_agencies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: AsyncClient = Depends(get_client),
):
    offset = (page - 1) * page_size
    res = await (
        client.table("agencies")
        .select("*")
        .eq("is_active", True)
        .order("avg_rating", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return res.data or []


@router.post("/agencies", response_model=AgencyOut, status_code=201)
async def create_agency(
    body: dict,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    # Only service-role / admin can create agencies in production
    # For dev, any authenticated user can create
    res = await client.table("agencies").insert(body).execute()
    return res.data[0]


# ─── Reviews ──────────────────────────────────────────────────────────────────

@router.post("/reviews", response_model=ReviewOut, status_code=201)
async def submit_review(
    body: ReviewCreate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Verify the student has a completed/enrolled application with this agency
    app_check = await (
        client.table("applications")
        .select("id")
        .eq("student_id", student["id"])
        .eq("agency_id", body.agency_id)
        .in_("status", ["enrolled", "offer_received", "visa_stage"])
        .limit(1)
        .execute()
    )
    if not app_check.data:
        raise HTTPException(
            status_code=403,
            detail="You can only review an agency after an offer, visa, or enrolment stage",
        )

    row = {
        "student_id":    student["id"],
        "agency_id":     body.agency_id,
        "consultant_id": body.consultant_id,
        "rating":        body.rating,
        "comment":       body.comment,
    }
    try:
        res = await client.table("reviews").insert(row).execute()
    except Exception:
        raise HTTPException(status_code=409, detail="You have already reviewed this agency")

    return res.data[0]


@router.get("/agencies/{agency_id}/reviews", response_model=list[ReviewOut])
async def get_agency_reviews(
    agency_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: AsyncClient = Depends(get_client),
):
    offset = (page - 1) * page_size
    res = await (
        client.table("reviews")
        .select("*")
        .eq("agency_id", agency_id)
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return res.data or []
