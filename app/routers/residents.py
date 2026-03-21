from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid

from app.database import get_db
from app.models.models import Resident, Flat, AppRole
from app.schemas.resident import ResidentCreate, ResidentUpdate, ResidentOut
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.utils.responses import success_response, paginated_response

router = APIRouter(tags=["residents"])


@router.get("/societies/{society_id}/residents")
async def list_residents(
    society_id: uuid.UUID,
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    block: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    q = select(Resident).where(Resident.society_id == society_id)
    if role:
        q = q.where(Resident.role == role)
    if active is not None:
        q = q.where(Resident.active == active)
    if search:
        q = q.where(Resident.name.ilike(f"%{search}%"))
    if block:
        q = q.join(Flat).where(Flat.block == block)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    residents = (await db.execute(q.offset((page - 1) * limit).limit(limit))).scalars().all()

    result = []
    for r in residents:
        flat = await db.get(Flat, r.flat_id)
        item = ResidentOut.model_validate(r).model_dump()
        item["flat_number"] = flat.flat_number if flat else None
        item["block"] = flat.block if flat else None
        result.append(item)

    return paginated_response(result, total, page, limit)


@router.post("/societies/{society_id}/residents", status_code=201)
async def create_resident(
    society_id: uuid.UUID,
    body: ResidentCreate,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    flat = await db.get(Flat, body.flat_id)
    if not flat or flat.society_id != society_id:
        raise HTTPException(status_code=404, detail="Flat not found in this society")

    resident = Resident(society_id=society_id, **body.model_dump())
    db.add(resident)

    if flat.occupancy == "vacant":
        flat.occupancy = "occupied"

    await db.commit()
    await db.refresh(resident)
    return success_response(ResidentOut.model_validate(resident).model_dump())


@router.put("/residents/{resident_id}")
async def update_resident(
    resident_id: uuid.UUID,
    body: ResidentUpdate,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    resident = await db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == resident.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(resident, field, value)
    await db.commit()
    await db.refresh(resident)
    return success_response(ResidentOut.model_validate(resident).model_dump())


@router.delete("/residents/{resident_id}")
async def deactivate_resident(
    resident_id: uuid.UUID,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    resident = await db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == resident.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    resident.active = False
    await db.commit()
    return success_response({"message": "Resident deactivated"})
