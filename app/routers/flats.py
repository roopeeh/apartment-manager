from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid

from app.database import get_db
from app.models.models import Flat, Resident, Payment
from app.schemas.flat import FlatCreate, FlatUpdate, FlatOut
from app.schemas.resident import ResidentOut
from app.schemas.payment import PaymentOut
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.models.models import AppRole
from app.utils.responses import success_response, paginated_response

router = APIRouter(tags=["flats"])


@router.get("/societies/{society_id}/flats")
async def list_flats(
    society_id: uuid.UUID,
    block: Optional[str] = Query(None),
    occupancy: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    q = select(Flat).where(Flat.society_id == society_id)
    if block:
        q = q.where(Flat.block == block)
    if occupancy:
        q = q.where(Flat.occupancy == occupancy)
    if search:
        q = q.where(Flat.flat_number.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    flats = (await db.execute(q.offset((page - 1) * limit).limit(limit))).scalars().all()

    return paginated_response(
        [FlatOut.model_validate(f).model_dump() for f in flats],
        total, page, limit
    )


@router.post("/societies/{society_id}/flats", status_code=201)
async def create_flat(
    society_id: uuid.UUID,
    body: FlatCreate,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    flat = Flat(society_id=society_id, **body.model_dump())
    db.add(flat)
    await db.commit()
    await db.refresh(flat)
    return success_response(FlatOut.model_validate(flat).model_dump())


@router.get("/flats/{flat_id}")
async def get_flat(
    flat_id: uuid.UUID,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    flat = await db.get(Flat, flat_id)
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")

    residents = (await db.execute(select(Resident).where(Resident.flat_id == flat_id))).scalars().all()
    payments = (await db.execute(select(Payment).where(Payment.flat_id == flat_id).order_by(Payment.year.desc(), Payment.month.desc()).limit(24))).scalars().all()

    return success_response({
        "flat": FlatOut.model_validate(flat).model_dump(),
        "residents": [ResidentOut.model_validate(r).model_dump() for r in residents],
        "payment_history": [
            {**PaymentOut.model_validate(p).model_dump(), "balance_due": p.balance_due}
            for p in payments
        ],
    })


@router.put("/flats/{flat_id}")
async def update_flat(
    flat_id: uuid.UUID,
    body: FlatUpdate,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    flat = await db.get(Flat, flat_id)
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == flat.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(flat, field, value)
    await db.commit()
    await db.refresh(flat)
    return success_response(FlatOut.model_validate(flat).model_dump())


@router.delete("/flats/{flat_id}")
async def delete_flat(
    flat_id: uuid.UUID,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    flat = await db.get(Flat, flat_id)
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == flat.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    await db.delete(flat)
    await db.commit()
    return success_response({"message": "Flat deleted"})
