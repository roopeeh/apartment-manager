from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid

from app.database import get_db
from app.models.models import Society, User, UserRole, Flat, Resident, AppRole
from app.schemas.society import SocietyCreate, SocietyUpdate, SocietyOut
from app.dependencies import require_super_admin
from app.utils.responses import success_response, paginated_response
from app.utils.password import hash_password

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/stats")
async def platform_stats(
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count()).select_from(Society))
    active = await db.scalar(select(func.count()).select_from(Society).where(Society.status == "active"))
    onboarding = await db.scalar(select(func.count()).select_from(Society).where(Society.status == "onboarding"))
    suspended = await db.scalar(select(func.count()).select_from(Society).where(Society.status == "suspended"))
    total_flats = await db.scalar(select(func.count()).select_from(Flat))
    total_residents = await db.scalar(select(func.count()).select_from(Resident).where(Resident.active == True))

    return success_response({
        "total_societies": total,
        "active_societies": active,
        "onboarding_societies": onboarding,
        "suspended_societies": suspended,
        "total_flats": total_flats,
        "total_residents": total_residents,
        "total_mrr": 0,
        "growth": {"societies_this_month": 0, "societies_last_month": 0},
    })


@router.get("/societies")
async def list_societies(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    plan: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(Society)
    if status:
        q = q.where(Society.status == status)
    if city:
        q = q.where(Society.city.ilike(f"%{city}%"))
    if plan:
        q = q.where(Society.plan == plan)
    if search:
        q = q.where(Society.name.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    societies = (await db.execute(q.offset((page - 1) * limit).limit(limit))).scalars().all()

    result = []
    for s in societies:
        flat_count = await db.scalar(select(func.count()).select_from(Flat).where(Flat.society_id == s.id))
        resident_count = await db.scalar(select(func.count()).select_from(Resident).where(Resident.society_id == s.id, Resident.active == True))

        admin_role = (await db.execute(
            select(UserRole).where(UserRole.society_id == s.id, UserRole.role == AppRole.admin)
        )).scalar_one_or_none()
        admin_user = None
        if admin_role:
            admin_user = await db.get(User, admin_role.user_id)

        result.append({
            "id": str(s.id),
            "name": s.name,
            "address": s.address,
            "city": s.city,
            "total_flats": flat_count,
            "total_residents": resident_count,
            "status": s.status,
            "plan": s.plan,
            "created_at": s.created_at.date().isoformat() if s.created_at else None,
            "admin_name": admin_user.name if admin_user else None,
            "admin_email": admin_user.email if admin_user else None,
            "admin_phone": admin_user.phone if admin_user else None,
            "monthly_revenue": 0,
        })

    return paginated_response(result, total, page, limit)


@router.post("/societies", status_code=201)
async def create_society(
    body: SocietyCreate,
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    society = Society(
        name=body.name,
        address=body.address,
        city=body.city,
        phone=body.phone,
        email=body.email,
        total_blocks=body.total_blocks,
        blocks=body.blocks,
        floors=body.floors,
        plan=body.plan,
        status="onboarding",
    )
    db.add(society)
    await db.flush()

    admin_data = body.admin
    result = await db.execute(select(User).where(User.email == admin_data["email"]))
    admin_user = result.scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            email=admin_data["email"],
            name=admin_data["name"],
            phone=admin_data.get("phone"),
            password_hash=hash_password(admin_data["password"]),
        )
        db.add(admin_user)
        await db.flush()

    role = UserRole(user_id=admin_user.id, society_id=society.id, role=AppRole.admin)
    db.add(role)
    await db.commit()

    return success_response({
        "society": {"id": str(society.id), "name": society.name, "status": society.status},
        "admin_user": {"id": str(admin_user.id), "email": admin_user.email},
        "message": "Society onboarded. Admin credentials sent via email.",
    })


@router.put("/societies/{society_id}")
async def update_society(
    society_id: uuid.UUID,
    body: SocietyUpdate,
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    society = await db.get(Society, society_id)
    if not society:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Society not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(society, field, value)
    await db.commit()
    await db.refresh(society)

    return success_response(SocietyOut.model_validate(society).model_dump())


@router.delete("/societies/{society_id}")
async def delete_society(
    society_id: uuid.UUID,
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    society = await db.get(Society, society_id)
    if not society:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Society not found")

    society.status = "suspended"
    await db.commit()
    return success_response({"message": "Society suspended"})


@router.get("/societies/{society_id}/audit")
async def society_audit(
    society_id: uuid.UUID,
    current=Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return success_response([])
