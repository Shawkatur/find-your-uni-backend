"""
GET  /universities          — paginated search with filters
GET  /universities/{id}     — detail + programs
POST /universities          — create (service role / admin only)
PATCH /universities/{id}    — update
GET  /universities/semantic — semantic vector search via pgvector
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import AsyncClient

from app.core.security import get_current_user
from app.db.client import get_client
from app.models.university import UniversityCreate
from app.services.ai import semantic_search_query

router = APIRouter(prefix="/universities", tags=["universities"])


@router.get("", response_model=list[dict])
async def list_universities(
    country: str | None = None,
    degree_level: str | None = None,
    field: str | None = None,
    max_tuition: int | None = None,
    scholarships_only: bool = False,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: AsyncClient = Depends(get_client),
):
    offset = (page - 1) * page_size
    query = client.table("universities").select(
        "*, programs(id, name, degree_level, field, tuition_usd_per_year, is_active)"
    )

    if country:
        query = query.eq("country", country.upper())
    if max_tuition is not None:
        query = query.lte("tuition_usd_per_year", max_tuition)
    if scholarships_only:
        query = query.eq("scholarships_available", True)
    if search:
        query = query.ilike("name", f"%{search}%")

    # degree_level / field filter handled via programs join
    if degree_level:
        query = query.eq("programs.degree_level", degree_level)
    if field:
        query = query.eq("programs.field", field)

    res = await query.order("ranking_qs", nulls_last=True).range(offset, offset + page_size - 1).execute()
    return res.data or []


@router.get("/semantic", response_model=list[dict])
async def semantic_search(
    q: str = Query(..., min_length=3, description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    client: AsyncClient = Depends(get_client),
):
    """
    Semantic search using pgvector cosine similarity.
    Example: 'engineering programs under 15k in Germany'
    """
    embedding = await semantic_search_query(q)
    # PostgREST RPC for vector similarity search
    res = await client.rpc(
        "match_universities",
        {
            "query_embedding": embedding,
            "match_threshold": 0.70,
            "match_count": limit,
        },
    ).execute()
    return res.data or []


@router.get("/{university_id}", response_model=dict)
async def get_university(
    university_id: str,
    client: AsyncClient = Depends(get_client),
):
    res = await (
        client.table("universities")
        .select("*, programs(*)")
        .eq("id", university_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="University not found")
    return res.data


@router.post("", response_model=dict, status_code=201)
async def create_university(
    body: UniversityCreate,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    role = (user.get("app_metadata") or {}).get("role", "student")
    if role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    row = body.model_dump()
    res = await client.table("universities").insert(row).execute()
    return res.data[0]


@router.patch("/{university_id}", response_model=dict)
async def update_university(
    university_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    role = (user.get("app_metadata") or {}).get("role", "student")
    if role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    res = await (
        client.table("universities")
        .update(body)
        .eq("id", university_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="University not found")
    return res.data[0]
