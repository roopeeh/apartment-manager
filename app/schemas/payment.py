from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, date
from decimal import Decimal


class PaymentCreate(BaseModel):
    flat_id: uuid.UUID
    month: str
    year: int
    amount_paid: Decimal
    payment_mode: Optional[str] = None
    payment_date: Optional[date] = None
    transaction_ref: Optional[str] = None
    remarks: Optional[str] = ""


class PaymentUpdate(BaseModel):
    amount_paid: Optional[Decimal] = None
    payment_mode: Optional[str] = None
    payment_date: Optional[date] = None
    transaction_ref: Optional[str] = None
    remarks: Optional[str] = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    flat_id: uuid.UUID
    month: str
    year: int
    maintenance_amount: Decimal
    amount_paid: Decimal
    balance_due: float
    status: str
    payment_date: Optional[date] = None
    payment_mode: Optional[str] = None
    transaction_ref: Optional[str] = None
    gateway_order_id: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime


class GenerateBillsRequest(BaseModel):
    month: str
    year: int


class CreateOrderRequest(BaseModel):
    flat_id: uuid.UUID
    month: str
    year: int
    amount: Decimal
