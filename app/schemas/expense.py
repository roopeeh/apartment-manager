from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, date
from decimal import Decimal


class ExpenseCreate(BaseModel):
    date: date
    title: str
    category: str
    vendor: Optional[str] = None
    amount: Decimal
    notes: Optional[str] = ""
    attachment_url: Optional[str] = None


class ExpenseUpdate(BaseModel):
    date: Optional[date] = None
    title: Optional[str] = None
    category: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    date: date
    title: str
    category: str
    vendor: Optional[str] = None
    amount: Decimal
    added_by: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None
    has_attachment: bool = False
    created_at: datetime

    @classmethod
    def from_orm_with_attachment(cls, obj):
        data = cls.model_validate(obj)
        data.has_attachment = bool(obj.attachment_url)
        return data
