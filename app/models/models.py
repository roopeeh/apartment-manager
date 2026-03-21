import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Numeric, Date,
    DateTime, ForeignKey, UniqueConstraint, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class AppRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    resident = "resident"


class Society(Base):
    __tablename__ = "societies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(255))
    logo_url = Column(Text)
    total_blocks = Column(Integer, default=0)
    blocks = Column(JSONB, default=list)
    floors = Column(JSONB, default=list)
    config = Column(JSONB, default=dict)
    payment_gateway = Column(JSONB, default=dict)
    plan = Column(String(20), default="basic")
    status = Column(String(20), default="onboarding")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    flats = relationship("Flat", back_populates="society", cascade="all, delete-orphan")
    residents = relationship("Resident", back_populates="society", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="society", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="society", cascade="all, delete-orphan")
    notices = relationship("Notice", back_populates="society", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="society", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(20))
    avatar_url = Column(Text)
    is_active = Column(Boolean, default=True)
    reset_token = Column(String(255))
    reset_token_expires = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=True)
    role = Column(SAEnum(AppRole, name="app_role"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "society_id", "role"),)

    user = relationship("User", back_populates="roles")
    society = relationship("Society", back_populates="user_roles")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    user = relationship("User", back_populates="refresh_tokens")


class Flat(Base):
    __tablename__ = "flats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    flat_number = Column(String(20), nullable=False)
    block = Column(String(10), nullable=False)
    floor = Column(Integer, nullable=False)
    area = Column(Integer)
    owner_name = Column(String(255))
    phone = Column(String(20))
    email = Column(String(255))
    occupancy = Column(String(10), default="vacant")
    maintenance_amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("society_id", "flat_number"),)

    society = relationship("Society", back_populates="flats")
    residents = relationship("Resident", back_populates="flat", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="flat", cascade="all, delete-orphan")


class Resident(Base):
    __tablename__ = "residents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    flat_id = Column(UUID(as_uuid=True), ForeignKey("flats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(20))
    email = Column(String(255))
    role = Column(String(20), nullable=False)
    active = Column(Boolean, default=True)
    move_in_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    society = relationship("Society", back_populates="residents")
    flat = relationship("Flat", back_populates="residents")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    flat_id = Column(UUID(as_uuid=True), ForeignKey("flats.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(3), nullable=False)
    year = Column(Integer, nullable=False)
    maintenance_amount = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), default=0)
    status = Column(String(10), default="unpaid")
    payment_date = Column(Date)
    payment_mode = Column(String(50))
    transaction_ref = Column(String(100))
    gateway_order_id = Column(String(100))
    remarks = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("society_id", "flat_id", "month", "year"),)

    society = relationship("Society", back_populates="payments")
    flat = relationship("Flat", back_populates="payments")

    @property
    def balance_due(self):
        return float(self.maintenance_amount) - float(self.amount_paid)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    vendor = Column(String(255))
    amount = Column(Numeric(10, 2), nullable=False)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, default="")
    attachment_url = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    society = relationship("Society", back_populates="expenses")


class Notice(Base):
    __tablename__ = "notices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id = Column(UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(String(10), default="medium")
    pinned = Column(Boolean, default=False)
    posted_by = Column(String(255))
    posted_date = Column(Date, default=date.today)
    expiry_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    society = relationship("Society", back_populates="notices")
