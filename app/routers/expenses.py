from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from sqlalchemy.orm import selectinload
from typing import Optional
import uuid
import os
import aiofiles
from datetime import date as date_type

from app.database import get_db
from app.models.models import Expense, ExpenseSplit, AppRole
from app.schemas.expense import ExpenseCreate, ExpenseUpdate, ExpenseOut
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.utils.responses import success_response, paginated_response
from app.config import settings
import json

router = APIRouter(tags=["expenses"])


@router.get("/societies/{society_id}/expenses/summary")
async def expense_summary(
    society_id: uuid.UUID,
    year: int = Query(...),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    all_expenses = (await db.execute(
        select(Expense).where(
            Expense.society_id == society_id,
            extract("year", Expense.date) == year,
        )
    )).scalars().all()

    monthly = {}
    by_category = {}
    for e in all_expenses:
        m = e.date.strftime("%b")
        monthly[m] = monthly.get(m, 0) + float(e.amount)
        by_category[e.category] = by_category.get(e.category, 0) + float(e.amount)

    return success_response({
        "monthly": [{"month": m, "total": monthly.get(m, 0)} for m in MONTHS if m in monthly],
        "by_category": [{"category": c, "amount": a} for c, a in by_category.items()],
        "total_ytd": sum(float(e.amount) for e in all_expenses),
    })


@router.get("/societies/{society_id}/expenses")
async def list_expenses(
    society_id: uuid.UUID,
    category: Optional[str] = Query(None),
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    q = select(Expense).where(Expense.society_id == society_id).options(selectinload(Expense.splits))
    if category:
        q = q.where(Expense.category == category)
    if month:
        q = q.where(extract("month", Expense.date) == month)
    if year:
        q = q.where(extract("year", Expense.date) == year)
    if search:
        q = q.where(Expense.title.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    expenses = (await db.execute(q.order_by(Expense.date.desc()).offset((page - 1) * limit).limit(limit))).scalars().all()

    result = []
    for e in expenses:
        item = ExpenseOut.model_validate(e).model_dump()
        item["has_attachment"] = bool(e.attachment_url)
        result.append(item)

    return paginated_response(result, total, page, limit)


@router.post("/societies/{society_id}/expenses", status_code=201)
async def create_expense(
    society_id: uuid.UUID,
    date: date_type = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    vendor: Optional[str] = Form(None),
    amount: float = Form(...),
    notes: Optional[str] = Form(""),
    attachment: Optional[UploadFile] = File(None),
    split_mode: Optional[str] = Form(None),
    splits: Optional[str] = Form(None),
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    attachment_url = None
    if attachment:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{attachment.filename}"
        filepath = os.path.join(settings.UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await attachment.read())
        attachment_url = f"/static/uploads/{filename}"

    user = current["user"]
    expense = Expense(
        society_id=society_id,
        date=date,
        title=title,
        category=category,
        vendor=vendor,
        amount=amount,
        notes=notes,
        attachment_url=attachment_url,
        added_by=user.id,
        split_mode=split_mode,
    )
    db.add(expense)
    await db.flush()

    # Handle splits if provided
    if split_mode and splits:
        try:
            splits_data = json.loads(splits)
            for split_item in splits_data:
                expense_split = ExpenseSplit(
                    expense_id=expense.id,
                    flat_id=uuid.UUID(split_item["flat_id"]),
                    amount=float(split_item["amount"]),
                )
                db.add(expense_split)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Invalid splits data: {str(e)}")

    await db.commit()
    await db.refresh(expense)

    item = ExpenseOut.model_validate(expense).model_dump()
    item["has_attachment"] = bool(expense.attachment_url)
    return success_response(item)


@router.put("/expenses/{expense_id}")
async def update_expense(
    expense_id: uuid.UUID,
    body: ExpenseUpdate,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    expense = await db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == expense.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(expense, field, value)
    await db.commit()
    await db.refresh(expense)
    item = ExpenseOut.model_validate(expense).model_dump()
    item["has_attachment"] = bool(expense.attachment_url)
    return success_response(item)


@router.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: uuid.UUID,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    expense = await db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == expense.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    await db.delete(expense)
    await db.commit()
    return success_response({"message": "Expense deleted"})
