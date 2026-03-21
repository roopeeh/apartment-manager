from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.database import get_db
from app.models.models import Society
from app.schemas.society import SocietyOut, SocietyUpdate
from app.dependencies import require_society_access, require_society_admin
from app.utils.responses import success_response

router = APIRouter(tags=["societies"])


@router.get("/societies/{society_id}")
async def get_society(
    society_id: uuid.UUID,
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    society = await db.get(Society, society_id)
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return success_response(SocietyOut.model_validate(society).model_dump())


@router.put("/societies/{society_id}")
async def update_society(
    society_id: uuid.UUID,
    body: SocietyUpdate,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    society = await db.get(Society, society_id)
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(society, field, value)
    await db.commit()
    await db.refresh(society)
    return success_response(SocietyOut.model_validate(society).model_dump())
