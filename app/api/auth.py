"""
POST /auth/student/register    — create student profile after Supabase signup
POST /auth/consultant/register — create consultant profile + link to agency
GET  /auth/me                  — return current user's profile
"""
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import AsyncClient

from app.core.security import get_current_user
from app.db.client import get_client
from app.db.queries import get_student_by_user_id
from app.models.student import StudentCreate, StudentOut
from app.models.application import ConsultantCreate, ConsultantOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/student/register", response_model=StudentOut, status_code=201)
async def register_student(
    body: StudentCreate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    user_id: str = user["sub"]

    # Prevent duplicate profiles
    existing = await get_student_by_user_id(client, user_id)
    if existing:
        raise HTTPException(status_code=409, detail="Student profile already exists")

    row = {
        "user_id":             user_id,
        "full_name":           body.full_name,
        "phone":               body.phone,
        "academic_history":    body.academic_history.model_dump(),
        "test_scores":         body.test_scores.model_dump(),
        "budget_usd_per_year": body.budget_usd_per_year,
        "preferred_countries": body.preferred_countries,
        "preferred_degree":    body.preferred_degree,
        "preferred_fields":    body.preferred_fields,
    }
    res = await client.table("students").insert(row).execute()
    return res.data[0]


@router.post("/consultant/register", response_model=ConsultantOut, status_code=201)
async def register_consultant(
    body: ConsultantCreate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    user_id: str = user["sub"]

    # Verify agency exists
    agency_res = await client.table("agencies").select("id").eq("id", body.agency_id).single().execute()
    if not agency_res.data:
        raise HTTPException(status_code=404, detail="Agency not found")

    # Prevent duplicate
    existing = await client.table("consultants").select("id").eq("user_id", user_id).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Consultant profile already exists")

    row = {
        "user_id":   user_id,
        "agency_id": body.agency_id,
        "role":      body.role,
        "full_name": body.full_name,
    }
    res = await client.table("consultants").insert(row).execute()

    # Set role in Supabase auth metadata
    await client.auth.admin.update_user_by_id(
        user_id,
        {"app_metadata": {"role": "consultant", "agency_id": body.agency_id}},
    )
    return res.data[0]


@router.get("/me")
async def get_me(
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    user_id: str = user["sub"]
    role = (user.get("app_metadata") or {}).get("role", "student")

    if role == "consultant":
        res = await client.table("consultants").select("*, agencies(*)").eq("user_id", user_id).single().execute()
        return {"role": "consultant", "profile": res.data}
    else:
        student = await get_student_by_user_id(client, user_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found. Please complete registration.")
        return {"role": "student", "profile": student}
