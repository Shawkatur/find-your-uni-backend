"""
POST  /applications                — student/consultant creates application
GET   /applications                — list my applications (student or consultant view)
GET   /applications/{id}           — detail
PATCH /applications/{id}/status    — state machine transition (consultant)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import AsyncClient

from app.core.security import get_current_user
from app.db.client import get_client
from app.db.queries import get_student_by_user_id, get_application
from app.models.application import (
    ApplicationCreate, ApplicationOut, ApplicationStatusUpdate, STATUS_TRANSITIONS
)
from app.services.notifications import notify_status_change, whatsapp_link, status_update_whatsapp_message

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(
    body: ApplicationCreate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    row = body.model_dump()
    row["status_history"] = [{
        "status":     "lead",
        "changed_by": user["sub"],
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "note":       "Application created",
    }]
    res = await client.table("applications").insert(row).execute()
    return res.data[0]


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    role = (user.get("app_metadata") or {}).get("role", "student")
    user_id = user["sub"]

    if role == "consultant":
        # Consultant sees all applications in their agency
        consultant_res = await client.table("consultants").select("agency_id").eq("user_id", user_id).single().execute()
        if not consultant_res.data:
            raise HTTPException(status_code=404, detail="Consultant profile not found")
        agency_id = consultant_res.data["agency_id"]
        res = await (
            client.table("applications")
            .select("*, programs(name, university_id), students(full_name, phone)")
            .eq("agency_id", agency_id)
            .order("updated_at", desc=True)
            .execute()
        )
    else:
        student = await get_student_by_user_id(client, user_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")
        res = await (
            client.table("applications")
            .select("*, programs(name, universities(name, country))")
            .eq("student_id", student["id"])
            .order("updated_at", desc=True)
            .execute()
        )

    return res.data or []


@router.get("/{app_id}", response_model=dict)
async def get_application_detail(
    app_id: str,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    res = await (
        client.table("applications")
        .select("*, programs(*, universities(*)), students(full_name, phone, academic_history, test_scores)")
        .eq("id", app_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Application not found")
    return res.data


@router.patch("/{app_id}/status", response_model=ApplicationOut)
async def update_status(
    app_id: str,
    body: ApplicationStatusUpdate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    app = await get_application(client, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    current_status = app["status"]
    new_status     = body.status

    # Validate state machine transition
    allowed = STATUS_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current_status} → {new_status}. Allowed: {allowed}",
        )

    # Append to status_history
    history: list = app.get("status_history") or []
    history.append({
        "status":     new_status,
        "changed_by": user["sub"],
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "note":       body.note,
    })

    res = await (
        client.table("applications")
        .update({"status": new_status, "status_history": history})
        .eq("id", app_id)
        .execute()
    )
    updated = res.data[0]

    # Notify student via Supabase Realtime
    student_res = await (
        client.table("students")
        .select("user_id, phone, full_name")
        .eq("id", app["student_id"])
        .single()
        .execute()
    )
    if student_res.data:
        student_data = student_res.data
        await notify_status_change(
            client,
            application_id=app_id,
            student_user_id=student_data["user_id"],
            new_status=new_status,
            note=body.note,
        )

    return updated


@router.get("/{app_id}/whatsapp")
async def get_whatsapp_link(
    app_id: str,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    """Generate a pre-filled WhatsApp link to message the student about their application."""
    res = await (
        client.table("applications")
        .select("status, students(full_name, phone), programs(name, universities(name))")
        .eq("id", app_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data    = res.data
    student_data = app_data.get("students") or {}
    program_data = app_data.get("programs") or {}
    uni_data     = program_data.get("universities") or {}

    phone = student_data.get("phone", "")
    if not phone:
        raise HTTPException(status_code=422, detail="Student has no phone number on record")

    message = status_update_whatsapp_message(
        student_name=student_data.get("full_name", "Student"),
        university_name=uni_data.get("name", "University"),
        program_name=program_data.get("name", "Program"),
        new_status=app_data["status"],
    )
    return {"whatsapp_url": whatsapp_link(phone, message)}
