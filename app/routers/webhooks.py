from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hmac
import hashlib
from datetime import date

from app.database import get_db
from app.models.models import Payment, Society
from fastapi import Depends

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/payment")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    payload = await request.json()
    order_id = payload.get("razorpay_order_id")
    payment_id = payload.get("razorpay_payment_id")
    razorpay_signature = payload.get("razorpay_signature")

    if not order_id:
        raise HTTPException(status_code=400, detail="Missing order_id")

    # Find the payment by order_id
    result = await db.execute(select(Payment).where(Payment.gateway_order_id == order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return {"status": "ok", "message": "Payment not found, skipping"}

    # Already processed
    if payment.status == "paid":
        return {"status": "ok", "message": "Already processed"}

    # Verify signature using society's webhook secret
    society = await db.get(Society, payment.society_id)
    if society and society.payment_gateway:
        webhook_secret = society.payment_gateway.get("webhook_secret", "")
        if webhook_secret and razorpay_signature:
            expected = hmac.new(
                webhook_secret.encode(),
                f"{order_id}|{payment_id}".encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, razorpay_signature):
                raise HTTPException(status_code=400, detail="Invalid signature")

    # Update payment
    payment.amount_paid = payment.maintenance_amount
    payment.status = "paid"
    payment.payment_date = date.today()
    payment.transaction_ref = payment_id
    payment.payment_mode = "Online"
    await db.commit()

    return {"status": "ok"}
