"""
POST /documents/upload     — generate pre-signed Cloudflare R2 upload URL
GET  /documents            — list my documents
DELETE /documents/{id}     — delete a document
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import boto3
from botocore.config import Config

from app.core.config import get_settings
from app.core.security import get_current_user
from app.db.client import get_client
from app.db.queries import get_student_by_user_id
from supabase import AsyncClient

router = APIRouter(prefix="/documents", tags=["documents"])


class UploadRequest(BaseModel):
    doc_type: str           # 'transcript' | 'passport' | 'ielts_cert' | etc.
    filename: str
    content_type: str       # e.g. 'application/pdf', 'image/jpeg'
    application_id: str | None = None


class UploadResponse(BaseModel):
    upload_url: str         # pre-signed PUT URL (valid for 15 min)
    document_id: str        # UUID for the document record
    object_key: str         # R2 object key to store after upload confirms


def _get_r2_client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{s.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=s.R2_ACCESS_KEY_ID,
        aws_secret_access_key=s.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


@router.post("/upload", response_model=UploadResponse)
async def generate_upload_url(
    body: UploadRequest,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    settings = get_settings()
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    doc_id = str(uuid.uuid4())
    ext    = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else "bin"
    key    = f"documents/{student['id']}/{doc_id}.{ext}"

    r2 = _get_r2_client()
    upload_url = r2.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket":      settings.R2_BUCKET_NAME,
            "Key":         key,
            "ContentType": body.content_type,
        },
        ExpiresIn=900,  # 15 minutes
    )

    # Create document record immediately (storage_url = object key)
    doc_row = {
        "id":             doc_id,
        "student_id":     student["id"],
        "doc_type":       body.doc_type,
        "storage_url":    key,
        "application_id": body.application_id,
    }
    await client.table("documents").insert(doc_row).execute()

    return UploadResponse(upload_url=upload_url, document_id=doc_id, object_key=key)


@router.get("", response_model=list[dict])
async def list_documents(
    application_id: str | None = None,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    query = client.table("documents").select("*").eq("student_id", student["id"])
    if application_id:
        query = query.eq("application_id", application_id)

    res = await query.order("uploaded_at", desc=True).execute()

    # Append public URL for each document
    settings = get_settings()
    docs = res.data or []
    for doc in docs:
        doc["public_url"] = f"{settings.R2_PUBLIC_URL}/{doc['storage_url']}"

    return docs


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
    client: AsyncClient = Depends(get_client),
):
    student = await get_student_by_user_id(client, user["sub"])
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Verify ownership
    res = await client.table("documents").select("id, storage_url").eq("id", doc_id).eq("student_id", student["id"]).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = res.data
    settings = get_settings()

    # Delete from R2
    try:
        r2 = _get_r2_client()
        r2.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=doc["storage_url"])
    except Exception as exc:
        print(f"[documents.py] R2 delete failed: {exc}")  # non-fatal

    # Delete DB record
    await client.table("documents").delete().eq("id", doc_id).execute()
