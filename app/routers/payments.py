from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid
from datetime import date

from app.database import get_db
from app.models.models import Payment, Flat, AppRole
from app.schemas.payment import PaymentCreate, PaymentUpdate, PaymentOut, GenerateBillsRequest, CreateOrderRequest
from app.dependencies import require_society_access, require_society_admin, get_current_user_with_roles
from app.utils.responses import success_response, paginated_response

router = APIRouter(tags=["payments"])

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
INT_TO_MONTH = {v: k for k, v in MONTH_MAP.items()}


def compute_status(maintenance_amount, amount_paid) -> str:
    balance = float(maintenance_amount) - float(amount_paid)
    if balance <= 0:
        return "paid"
    elif float(amount_paid) > 0:
        return "partial"
    return "unpaid"


@router.get("/societies/{society_id}/payments/summary")
async def payment_summary(
    society_id: uuid.UUID,
    year: int = Query(...),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    months = list(INT_TO_MONTH.values())
    result = []
    for month in months:
        payments = (await db.execute(
            select(Payment).where(Payment.society_id == society_id, Payment.month == month, Payment.year == year)
        )).scalars().all()
        if not payments:
            continue
        total_expected = sum(float(p.maintenance_amount) for p in payments)
        total_collected = sum(float(p.amount_paid) for p in payments)
        paid = sum(1 for p in payments if p.status == "paid")
        unpaid = sum(1 for p in payments if p.status == "unpaid")
        partial = sum(1 for p in payments if p.status == "partial")
        result.append({
            "month": month,
            "year": year,
            "total_expected": total_expected,
            "total_collected": total_collected,
            "total_pending": total_expected - total_collected,
            "paid_count": paid,
            "unpaid_count": unpaid,
            "partial_count": partial,
            "collection_percentage": round((total_collected / total_expected * 100) if total_expected > 0 else 0, 1),
        })
    return success_response(result)


@router.get("/societies/{society_id}/payments")
async def list_payments(
    society_id: uuid.UUID,
    month: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    block: Optional[str] = Query(None),
    flat_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    # Resident can only see own flat
    roles = current["roles"]
    user = current["user"]
    is_resident_only = all(
        r.role == AppRole.resident for r in roles if r.society_id == society_id
    ) and not any(r.role in (AppRole.admin, AppRole.super_admin) for r in roles)

    q = select(Payment).where(Payment.society_id == society_id)
    if month:
        q = q.where(Payment.month == month)
    if year:
        q = q.where(Payment.year == year)
    if status:
        q = q.where(Payment.status == status)
    if flat_id:
        q = q.where(Payment.flat_id == flat_id)
    if block:
        q = q.join(Flat).where(Flat.block == block)

    if is_resident_only:
        # find resident's flat
        from app.models.models import Resident
        res = (await db.execute(
            select(Resident).where(Resident.society_id == society_id, Resident.user_id == user.id, Resident.active == True)
        )).scalar_one_or_none()
        if res:
            q = q.where(Payment.flat_id == res.flat_id)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    payments = (await db.execute(q.offset((page - 1) * limit).limit(limit))).scalars().all()

    result = []
    for p in payments:
        flat = await db.get(Flat, p.flat_id)
        item = PaymentOut.model_validate(p).model_dump()
        item["balance_due"] = p.balance_due
        item["flat_number"] = flat.flat_number if flat else None
        item["block"] = flat.block if flat else None
        item["owner_name"] = flat.owner_name if flat else None
        result.append(item)

    return paginated_response(result, total, page, limit)


@router.post("/societies/{society_id}/payments", status_code=201)
async def record_payment(
    society_id: uuid.UUID,
    body: PaymentCreate,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    flat = await db.get(Flat, body.flat_id)
    if not flat or flat.society_id != society_id:
        raise HTTPException(status_code=404, detail="Flat not found in this society")

    result = await db.execute(
        select(Payment).where(
            Payment.society_id == society_id,
            Payment.flat_id == body.flat_id,
            Payment.month == body.month,
            Payment.year == body.year,
        )
    )
    payment = result.scalar_one_or_none()

    if payment:
        new_paid = float(payment.amount_paid) + float(body.amount_paid)
        payment.amount_paid = new_paid
        payment.payment_mode = body.payment_mode or payment.payment_mode
        payment.payment_date = body.payment_date or payment.payment_date
        payment.transaction_ref = body.transaction_ref or payment.transaction_ref
        payment.remarks = body.remarks if body.remarks else payment.remarks
        payment.status = compute_status(payment.maintenance_amount, payment.amount_paid)
    else:
        payment = Payment(
            society_id=society_id,
            flat_id=body.flat_id,
            month=body.month,
            year=body.year,
            maintenance_amount=flat.maintenance_amount,
            amount_paid=body.amount_paid,
            payment_mode=body.payment_mode,
            payment_date=body.payment_date,
            transaction_ref=body.transaction_ref,
            remarks=body.remarks,
            status=compute_status(flat.maintenance_amount, body.amount_paid),
        )
        db.add(payment)

    await db.commit()
    await db.refresh(payment)
    item = PaymentOut.model_validate(payment).model_dump()
    item["balance_due"] = payment.balance_due
    return success_response(item)


@router.put("/payments/{payment_id}")
async def update_payment(
    payment_id: uuid.UUID,
    body: PaymentUpdate,
    current=Depends(get_current_user_with_roles),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    roles = current["roles"]
    has_access = any(
        r.role in (AppRole.admin, AppRole.super_admin) and
        (r.role == AppRole.super_admin or r.society_id == payment.society_id)
        for r in roles
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Admin access required")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(payment, field, value)
    payment.status = compute_status(payment.maintenance_amount, payment.amount_paid)
    await db.commit()
    await db.refresh(payment)
    item = PaymentOut.model_validate(payment).model_dump()
    item["balance_due"] = payment.balance_due
    return success_response(item)


@router.post("/societies/{society_id}/payments/generate-bills", status_code=201)
async def generate_bills(
    society_id: uuid.UUID,
    body: GenerateBillsRequest,
    current=Depends(require_society_admin),
    db: AsyncSession = Depends(get_db),
):
    flats = (await db.execute(
        select(Flat).where(Flat.society_id == society_id, Flat.occupancy == "occupied")
    )).scalars().all()

    generated = 0
    skipped = 0
    for flat in flats:
        existing = await db.execute(
            select(Payment).where(
                Payment.society_id == society_id,
                Payment.flat_id == flat.id,
                Payment.month == body.month,
                Payment.year == body.year,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        payment = Payment(
            society_id=society_id,
            flat_id=flat.id,
            month=body.month,
            year=body.year,
            maintenance_amount=flat.maintenance_amount,
            amount_paid=0,
            status="unpaid",
        )
        db.add(payment)
        generated += 1

    all_flats = (await db.execute(select(Flat).where(Flat.society_id == society_id, Flat.occupancy == "vacant"))).scalars().all()
    vacant_count = len(all_flats)

    await db.commit()
    return success_response({
        "generated": generated,
        "skipped": skipped,
        "message": f"{generated} bills generated for {body.month} {body.year}. {vacant_count} vacant flats skipped.",
    })


@router.post("/societies/{society_id}/payments/create-order")
async def create_order(
    society_id: uuid.UUID,
    body: CreateOrderRequest,
    current=Depends(require_society_access),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import Society
    society = await db.get(Society, society_id)
    flat = await db.get(Flat, body.flat_id)
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")

    receipt = f"{society.name[:2].upper()}-{flat.flat_number}-{body.month.upper()}-{body.year}"
    # Stub: in production, call Razorpay API here
    order_id = f"order_stub_{uuid.uuid4().hex[:10]}"

    # Save order_id to payment record
    result = await db.execute(
        select(Payment).where(
            Payment.society_id == society_id,
            Payment.flat_id == body.flat_id,
            Payment.month == body.month,
            Payment.year == body.year,
        )
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.gateway_order_id = order_id
        await db.commit()

    return success_response({
        "order_id": order_id,
        "gateway_key": society.payment_gateway.get("key_id", "") if society.payment_gateway else "",
        "amount": int(float(body.amount) * 100),
        "currency": "INR",
        "receipt": receipt,
    })
