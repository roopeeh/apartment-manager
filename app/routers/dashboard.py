from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from typing import Optional
import uuid
from datetime import date

from app.database import get_db
from app.models.models import Flat, Resident, Payment, Expense, Notice, AppRole
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.utils.responses import success_response
from app.schemas.payment import PaymentOut
from app.schemas.expense import ExpenseOut
from app.schemas.notice import NoticeOut

router = APIRouter(tags=["dashboard"])

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.get("/societies/{society_id}/dashboard")
async def admin_dashboard(
    society_id: uuid.UUID,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    current_month = today.strftime("%b")
    current_year = today.year

    total_flats = await db.scalar(select(func.count()).select_from(Flat).where(Flat.society_id == society_id))
    occupied = await db.scalar(select(func.count()).select_from(Flat).where(Flat.society_id == society_id, Flat.occupancy == "occupied"))
    vacant = total_flats - occupied

    # Current month payments
    cm_payments = (await db.execute(
        select(Payment).where(Payment.society_id == society_id, Payment.month == current_month, Payment.year == current_year)
    )).scalars().all()

    total_expected = sum(float(p.maintenance_amount) for p in cm_payments)
    total_collected = sum(float(p.amount_paid) for p in cm_payments)
    paid_count = sum(1 for p in cm_payments if p.status == "paid")
    unpaid_count = sum(1 for p in cm_payments if p.status == "unpaid")
    partial_count = sum(1 for p in cm_payments if p.status == "partial")

    # Current month expenses
    cm_expenses = (await db.execute(
        select(Expense).where(
            Expense.society_id == society_id,
            extract("month", Expense.date) == today.month,
            extract("year", Expense.date) == current_year,
        )
    )).scalars().all()
    total_expenses = sum(float(e.amount) for e in cm_expenses)

    # Monthly collection (last 12 months)
    monthly_collection = []
    for m in MONTHS:
        payments = (await db.execute(
            select(Payment).where(Payment.society_id == society_id, Payment.month == m, Payment.year == current_year)
        )).scalars().all()
        if payments:
            monthly_collection.append({
                "month": m,
                "collected": sum(float(p.amount_paid) for p in payments),
                "expected": sum(float(p.maintenance_amount) for p in payments),
                "pending": sum(p.balance_due for p in payments),
            })

    # Monthly expenses
    monthly_expenses = []
    for idx, m in enumerate(MONTHS):
        exps = (await db.execute(
            select(Expense).where(
                Expense.society_id == society_id,
                extract("month", Expense.date) == idx + 1,
                extract("year", Expense.date) == current_year,
            )
        )).scalars().all()
        if exps:
            monthly_expenses.append({"month": m, "total": sum(float(e.amount) for e in exps)})

    # Expense categories this year
    all_expenses = (await db.execute(
        select(Expense).where(Expense.society_id == society_id, extract("year", Expense.date) == current_year)
    )).scalars().all()
    category_map = {}
    for e in all_expenses:
        category_map[e.category] = category_map.get(e.category, 0) + float(e.amount)
    expense_categories = [{"category": c, "amount": a} for c, a in category_map.items()]

    # Recent expenses
    recent_expenses_q = (await db.execute(
        select(Expense).where(Expense.society_id == society_id).order_by(Expense.created_at.desc()).limit(5)
    )).scalars().all()
    recent_expenses = [ExpenseOut.model_validate(e).model_dump() for e in recent_expenses_q]

    # Pending flats this month
    pending = (await db.execute(
        select(Payment).where(
            Payment.society_id == society_id,
            Payment.month == current_month,
            Payment.year == current_year,
            Payment.status != "paid",
        )
    )).scalars().all()
    pending_flats = []
    for p in pending[:10]:
        flat = await db.get(Flat, p.flat_id)
        item = PaymentOut.model_validate(p).model_dump()
        item["balance_due"] = p.balance_due
        item["flat_number"] = flat.flat_number if flat else None
        pending_flats.append(item)

    # Recent notices
    recent_notices_q = (await db.execute(
        select(Notice).where(Notice.society_id == society_id).order_by(Notice.created_at.desc()).limit(4)
    )).scalars().all()
    recent_notices = [NoticeOut.model_validate(n).model_dump() for n in recent_notices_q]

    return success_response({
        "total_flats": total_flats,
        "occupied_flats": occupied,
        "vacant_flats": vacant,
        "current_month": {
            "month": current_month,
            "year": current_year,
            "total_expected": total_expected,
            "total_collected": total_collected,
            "total_pending": total_expected - total_collected,
            "total_expenses": total_expenses,
            "net_balance": total_collected - total_expenses,
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
            "partial_count": partial_count,
            "collection_percentage": round((total_collected / total_expected * 100) if total_expected else 0, 1),
        },
        "monthly_collection": monthly_collection,
        "monthly_expenses": monthly_expenses,
        "expense_categories": expense_categories,
        "recent_expenses": recent_expenses,
        "pending_flats": pending_flats,
        "recent_notices": recent_notices,
    })


@router.get("/societies/{society_id}/resident-dashboard")
async def resident_dashboard(
    society_id: uuid.UUID,
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    current_month = today.strftime("%b")
    current_year = today.year
    user = current["user"]

    resident = (await db.execute(
        select(Resident).where(
            Resident.society_id == society_id,
            Resident.user_id == user.id,
            Resident.active == True,
        )
    )).scalar_one_or_none()

    flat = None
    if resident:
        flat = await db.get(Flat, resident.flat_id)

    current_payment = None
    payment_history = []
    if flat:
        cp = (await db.execute(
            select(Payment).where(
                Payment.flat_id == flat.id,
                Payment.month == current_month,
                Payment.year == current_year,
            )
        )).scalar_one_or_none()
        if cp:
            current_payment = {
                "month": cp.month,
                "year": cp.year,
                "status": cp.status,
                "amount_due": float(cp.maintenance_amount),
                "balance_due": cp.balance_due,
            }

        history = (await db.execute(
            select(Payment).where(Payment.flat_id == flat.id).order_by(Payment.year.desc(), Payment.month.desc()).limit(12)
        )).scalars().all()
        for p in history:
            item = PaymentOut.model_validate(p).model_dump()
            item["balance_due"] = p.balance_due
            payment_history.append(item)

    # Community summary
    cm_payments = (await db.execute(
        select(Payment).where(Payment.society_id == society_id, Payment.month == current_month, Payment.year == current_year)
    )).scalars().all()
    cm_expenses = (await db.execute(
        select(Expense).where(
            Expense.society_id == society_id,
            extract("month", Expense.date) == today.month,
            extract("year", Expense.date) == current_year,
        )
    )).scalars().all()

    total_expected = sum(float(p.maintenance_amount) for p in cm_payments)
    total_collected = sum(float(p.amount_paid) for p in cm_payments)
    total_expenses = sum(float(e.amount) for e in cm_expenses)

    recent_expenses_q = (await db.execute(
        select(Expense).where(Expense.society_id == society_id).order_by(Expense.created_at.desc()).limit(5)
    )).scalars().all()
    recent_notices_q = (await db.execute(
        select(Notice).where(Notice.society_id == society_id).order_by(Notice.pinned.desc(), Notice.created_at.desc()).limit(4)
    )).scalars().all()

    return success_response({
        "flat": {
            "id": str(flat.id),
            "flat_number": flat.flat_number,
            "block": flat.block,
            "floor": flat.floor,
            "area": flat.area,
            "maintenance_amount": float(flat.maintenance_amount),
        } if flat else None,
        "current_payment": current_payment,
        "payment_history": payment_history,
        "community_summary": {
            "total_collected_this_month": total_collected,
            "total_expenses_this_month": total_expenses,
            "collection_percentage": round((total_collected / total_expected * 100) if total_expected else 0, 1),
        },
        "recent_expenses": [ExpenseOut.model_validate(e).model_dump() for e in recent_expenses_q],
        "recent_notices": [NoticeOut.model_validate(n).model_dump() for n in recent_notices_q],
    })


@router.get("/societies/{society_id}/reports")
async def reports(
    society_id: uuid.UUID,
    type: str = Query(...),
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    if type == "collection":
        month_str = MONTHS[month - 1] if month else date.today().strftime("%b")
        yr = year or date.today().year
        payments = (await db.execute(
            select(Payment).where(Payment.society_id == society_id, Payment.month == month_str, Payment.year == yr)
        )).scalars().all()
        details = []
        for p in payments:
            flat = await db.get(Flat, p.flat_id)
            details.append({
                "flat_number": flat.flat_number if flat else None,
                "block": flat.block if flat else None,
                "owner_name": flat.owner_name if flat else None,
                "amount_due": float(p.maintenance_amount),
                "amount_paid": float(p.amount_paid),
                "balance_due": p.balance_due,
                "status": p.status,
            })
        total_expected = sum(float(p.maintenance_amount) for p in payments)
        total_collected = sum(float(p.amount_paid) for p in payments)
        return success_response({
            "type": "collection",
            "period": {"month": month_str, "year": yr},
            "summary": {"total_expected": total_expected, "total_collected": total_collected},
            "details": details,
        })

    elif type == "expense":
        yr = year or date.today().year
        q = select(Expense).where(Expense.society_id == society_id, extract("year", Expense.date) == yr)
        if month:
            q = q.where(extract("month", Expense.date) == month)
        expenses = (await db.execute(q)).scalars().all()
        return success_response({
            "type": "expense",
            "period": {"month": month, "year": yr},
            "total": sum(float(e.amount) for e in expenses),
            "details": [ExpenseOut.model_validate(e).model_dump() for e in expenses],
        })

    elif type == "outstanding":
        yr = year or date.today().year
        payments = (await db.execute(
            select(Payment).where(Payment.society_id == society_id, Payment.year == yr, Payment.status != "paid")
        )).scalars().all()
        details = []
        for p in payments:
            flat = await db.get(Flat, p.flat_id)
            details.append({
                "flat_number": flat.flat_number if flat else None,
                "block": flat.block if flat else None,
                "owner_name": flat.owner_name if flat else None,
                "month": p.month,
                "year": p.year,
                "balance_due": p.balance_due,
                "status": p.status,
            })
        return success_response({
            "type": "outstanding",
            "year": yr,
            "total_outstanding": sum(p.balance_due for p in payments),
            "details": details,
        })

    elif type == "yearly_summary":
        yr = year or date.today().year
        summary = []
        for idx, m in enumerate(MONTHS):
            payments = (await db.execute(
                select(Payment).where(Payment.society_id == society_id, Payment.month == m, Payment.year == yr)
            )).scalars().all()
            expenses = (await db.execute(
                select(Expense).where(
                    Expense.society_id == society_id,
                    extract("month", Expense.date) == idx + 1,
                    extract("year", Expense.date) == yr,
                )
            )).scalars().all()
            collected = sum(float(p.amount_paid) for p in payments)
            exp_total = sum(float(e.amount) for e in expenses)
            summary.append({
                "month": m,
                "collected": collected,
                "expenses": exp_total,
                "net": collected - exp_total,
            })
        return success_response({"type": "yearly_summary", "year": yr, "months": summary})

    raise HTTPException(status_code=400, detail="Invalid report type. Use: collection, expense, outstanding, yearly_summary")
