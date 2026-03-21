from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import os
import aiofiles

from app.database import get_db
from app.dependencies import require_super_admin, get_current_user_with_roles
from app.models.models import AppRole
from app.utils.responses import success_response
from app.config import settings

router = APIRouter(tags=["upload"])

ALLOWED_TYPES = {"expense_receipt", "notice_image", "society_logo"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    type: str = Form(...),
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    roles = current["roles"]
    has_access = any(r.role in (AppRole.admin, AppRole.super_admin) for r in roles)
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    if type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Allowed: {', '.join(ALLOWED_TYPES)}")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    content = await file.read()
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    return success_response({
        "url": f"/static/uploads/{filename}",
        "filename": file.filename,
        "size": len(content),
        "content_type": file.content_type,
    })
