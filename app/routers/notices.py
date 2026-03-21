from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid
from datetime import date

from app.database import get_db
from app.models.models import Notice, AppRole
from app.schemas.notice import NoticeCreate, NoticeUpdate, NoticeOut
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.utils.responses import success_response
from app.models.models import User

router = APIRouter(tags=["notices"])


@router.get("/societies/{society_id}/notices")
async def list_notices(
    society_id: uuid.UUID,
    priority: Optional[str] = Query(None),
    pinned: Optional[bool] = Query(None),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    q = select(Notice).where(Notice.society_id == society_id)
    if priority:
        q = q.where(Notice.priority == priority)
    if pinned is not None:
        q = q.where(Notice.pinned == pinned)

    q = q.order_by(Notice.pinned.desc(), Notice.created_at.desc())
    notices = (await db.execute(q)).scalars().all()

    return success_response([NoticeOut.model_validate(n).model_dump() for n in notices])


@router.post("/societies/{society_id}/notices", status_code=201)
async def create_notice(
    society_id: uuid.UUID,
    body: NoticeCreate,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    user: User = current["user"]
    notice = Notice(
        society_id=society_id,
        title=body.title,
        message=body.message,
        priority=body.priority,
        pinned=body.pinned,
        expiry_date=body.expiry_date,
        posted_by=user.name,
        posted_date=date.today(),
    )
    db.add(notice)
    await db.commit()
    await db.refresh(notice)
    return success_response(NoticeOut.model_validate(notice).model_dump())


@router.put("/notices/{notice_id}")
async def update_notice(
    notice_id: uuid.UUID,
    body: NoticeUpdate,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    notice = await db.get(Notice, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == notice.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(notice, field, value)
    await db.commit()
    await db.refresh(notice)
    return success_response(NoticeOut.model_validate(notice).model_dump())


@router.delete("/notices/{notice_id}")
async def delete_notice(
    notice_id: uuid.UUID,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    notice = await db.get(Notice, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == notice.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    await db.delete(notice)
    await db.commit()
    return success_response({"message": "Notice deleted"})
