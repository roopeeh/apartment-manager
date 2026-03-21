# Complete API Specification — Apartment Maintenance SaaS

> **Use this document as a prompt for your backend developer or AI code generator to build the entire REST API.**

---

## Overview

Multi-tenant SaaS for apartment/housing society maintenance management. Three user roles: **Super Admin** (platform owner), **Admin** (society-level manager), **Resident** (flat occupant). Every society is an isolated tenant identified by `society_id`.

**Base URL:** `https://your-api-domain.com/api/v1`

**Auth:** JWT Bearer tokens. All endpoints (except `/auth/*`) require `Authorization: Bearer <access_token>`.

---

## 1. DATABASE SCHEMA

### 1.1 `societies`
```sql
CREATE TABLE societies (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          VARCHAR(255) NOT NULL,
  address       TEXT NOT NULL,
  city          VARCHAR(100) NOT NULL,
  phone         VARCHAR(20),
  email         VARCHAR(255),
  logo_url      TEXT,
  total_blocks  INT DEFAULT 0,
  blocks        JSONB DEFAULT '[]',        -- e.g. ["A","B","C"]
  floors        JSONB DEFAULT '[]',        -- e.g. [1,2,3,4,5]
  config        JSONB DEFAULT '{}',        -- billing defaults, late fees, receipt prefix
  payment_gateway JSONB DEFAULT '{}',      -- { provider, merchant_id, api_key, api_secret } — ENCRYPTED
  plan          VARCHAR(20) DEFAULT 'basic', -- basic | pro | enterprise
  status        VARCHAR(20) DEFAULT 'onboarding', -- active | onboarding | suspended
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);
```

### 1.2 `users`
```sql
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,     -- bcrypt or argon2
  name          VARCHAR(255) NOT NULL,
  phone         VARCHAR(20),
  avatar_url    TEXT,
  is_active     BOOLEAN DEFAULT true,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);
```

### 1.3 `user_roles`
```sql
CREATE TYPE app_role AS ENUM ('super_admin', 'admin', 'resident');

CREATE TABLE user_roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  society_id  UUID REFERENCES societies(id) ON DELETE CASCADE,  -- NULL for super_admin
  role        app_role NOT NULL,
  UNIQUE(user_id, society_id, role)
);
```

### 1.4 `flats`
```sql
CREATE TABLE flats (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id          UUID NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  flat_number         VARCHAR(20) NOT NULL,    -- e.g. "A101"
  block               VARCHAR(10) NOT NULL,
  floor               INT NOT NULL,
  area                INT,                     -- sq ft
  owner_name          VARCHAR(255),
  phone               VARCHAR(20),
  email               VARCHAR(255),
  occupancy           VARCHAR(10) DEFAULT 'vacant', -- occupied | vacant
  maintenance_amount  DECIMAL(10,2) NOT NULL,
  created_at          TIMESTAMPTZ DEFAULT now(),
  UNIQUE(society_id, flat_number)
);
```

### 1.5 `residents`
```sql
CREATE TABLE residents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id    UUID NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  flat_id       UUID NOT NULL REFERENCES flats(id) ON DELETE CASCADE,
  user_id       UUID REFERENCES users(id),   -- linked when resident creates account
  name          VARCHAR(255) NOT NULL,
  phone         VARCHAR(20),
  email         VARCHAR(255),
  role          VARCHAR(20) NOT NULL,         -- Owner | Tenant | Family Member
  active        BOOLEAN DEFAULT true,
  move_in_date  DATE,
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

### 1.6 `payments`
```sql
CREATE TABLE payments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id          UUID NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  flat_id             UUID NOT NULL REFERENCES flats(id) ON DELETE CASCADE,
  month               VARCHAR(3) NOT NULL,       -- Jan, Feb, ...
  year                INT NOT NULL,
  maintenance_amount  DECIMAL(10,2) NOT NULL,
  amount_paid         DECIMAL(10,2) DEFAULT 0,
  balance_due         DECIMAL(10,2) GENERATED ALWAYS AS (maintenance_amount - amount_paid) STORED,
  status              VARCHAR(10) DEFAULT 'unpaid', -- paid | unpaid | partial
  payment_date        DATE,
  payment_mode        VARCHAR(50),               -- UPI | Bank Transfer | Cash | Cheque | Online
  transaction_ref     VARCHAR(100),
  gateway_order_id    VARCHAR(100),
  remarks             TEXT DEFAULT '',
  created_at          TIMESTAMPTZ DEFAULT now(),
  UNIQUE(society_id, flat_id, month, year)
);
```

### 1.7 `expenses`
```sql
CREATE TABLE expenses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id      UUID NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  title           VARCHAR(255) NOT NULL,
  category        VARCHAR(100) NOT NULL,
  vendor          VARCHAR(255),
  amount          DECIMAL(10,2) NOT NULL,
  added_by        UUID REFERENCES users(id),
  notes           TEXT DEFAULT '',
  attachment_url  TEXT,                      -- S3/storage URL
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

### 1.8 `notices`
```sql
CREATE TABLE notices (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id    UUID NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  title         VARCHAR(255) NOT NULL,
  message       TEXT NOT NULL,
  priority      VARCHAR(10) DEFAULT 'medium',  -- high | medium | low
  pinned        BOOLEAN DEFAULT false,
  posted_by     VARCHAR(255),
  posted_date   DATE DEFAULT CURRENT_DATE,
  expiry_date   DATE,
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

---

## 2. COMPLETE API ENDPOINTS

### Standard Response Format
```json
// Success
{ "success": true, "data": { ... } }

// List with pagination
{ "success": true, "data": [...], "pagination": { "total": 100, "page": 1, "limit": 50, "pages": 2 } }

// Error
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "Email is required" } }
```

### Standard HTTP Status Codes
| Code | Usage |
|------|-------|
| 200 | Success |
| 201 | Created |
| 400 | Validation error |
| 401 | Unauthorized (invalid/expired token) |
| 403 | Forbidden (insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (duplicate) |
| 500 | Internal server error |

---

### 2.1 AUTHENTICATION (`/auth`)

#### `POST /auth/register`
Create a new user account. Used during onboarding.
```
Request:
{
  "name": "Rahul Sharma",
  "email": "rahul@example.com",
  "password": "securePassword123",
  "phone": "+91 98765 43210"
}

Response (201):
{
  "success": true,
  "data": {
    "user": { "id": "uuid", "name": "Rahul Sharma", "email": "rahul@example.com" },
    "message": "Account created. Please contact your society admin for role assignment."
  }
}
```

#### `POST /auth/login`
```
Request:
{
  "email": "rahul@example.com",
  "password": "securePassword123"
}

Response (200):
{
  "success": true,
  "data": {
    "access_token": "eyJhbG...",
    "refresh_token": "eyJhbG...",
    "user": {
      "id": "user-uuid",
      "name": "Rahul Sharma",
      "email": "rahul@example.com"
    },
    "roles": [
      {
        "society_id": "society-uuid",
        "role": "admin",
        "society_name": "Greenview Residency"
      }
    ]
  }
}

Error (401):
{
  "success": false,
  "error": { "code": "INVALID_CREDENTIALS", "message": "Invalid email or password" }
}
```

#### `POST /auth/refresh`
```
Request: { "refresh_token": "eyJhbG..." }
Response: { "success": true, "data": { "access_token": "new...", "refresh_token": "new..." } }
```

#### `POST /auth/forgot-password`
Sends a password reset email with a tokenized link.
```
Request: { "email": "rahul@example.com" }
Response: { "success": true, "data": { "message": "If account exists, reset link sent to email" } }
```

#### `POST /auth/reset-password`
```
Request: { "token": "reset-token-from-email", "new_password": "newSecurePassword" }
Response: { "success": true, "data": { "message": "Password updated successfully" } }
```

#### `POST /auth/logout`
Invalidates the refresh token.
```
Request: { "refresh_token": "eyJhbG..." }
Response: { "success": true, "data": { "message": "Logged out" } }
```

#### `POST /auth/change-password`
Authenticated. Change password for logged-in user.
```
Request: { "current_password": "old", "new_password": "new" }
Response: { "success": true, "data": { "message": "Password changed" } }
```

---

### 2.2 PLATFORM / SUPER ADMIN (`/platform`)

> **Role required:** `super_admin`

#### `GET /platform/stats`
Platform-wide aggregated metrics.
```
Response:
{
  "success": true,
  "data": {
    "total_societies": 6,
    "active_societies": 4,
    "onboarding_societies": 1,
    "suspended_societies": 1,
    "total_flats": 532,
    "total_residents": 456,
    "total_mrr": 22000,
    "growth": {
      "societies_this_month": 1,
      "societies_last_month": 0
    }
  }
}
```

#### `GET /platform/societies`
List all societies with summary stats.
```
Query: ?status=active&search=green&city=Bangalore&plan=pro&page=1&limit=20

Response:
{
  "success": true,
  "data": [
    {
      "id": "society-uuid",
      "name": "Greenview Residency",
      "address": "14, MG Road, Koramangala",
      "city": "Bangalore",
      "total_flats": 55,
      "total_residents": 48,
      "status": "active",
      "plan": "pro",
      "created_at": "2024-06-15",
      "admin_name": "Rajesh Kumar",
      "admin_email": "admin@greenview.in",
      "admin_phone": "+91 98765 43210",
      "monthly_revenue": 4500
    }
  ],
  "pagination": { "total": 6, "page": 1, "limit": 20, "pages": 1 }
}
```

#### `POST /platform/societies`
Onboard a new apartment society + create admin user.
```
Request:
{
  "name": "Sunrise Apartments",
  "address": "22, Whitefield Main Road",
  "city": "Bangalore",
  "phone": "+91 80 1234 5678",
  "email": "info@sunrise.in",
  "total_blocks": 4,
  "blocks": ["A", "B", "C", "D"],
  "floors": [1, 2, 3, 4, 5, 6],
  "plan": "pro",
  "admin": {
    "name": "Priya Sharma",
    "email": "priya@sunrise.in",
    "phone": "+91 98765 12345",
    "password": "tempPassword123"
  }
}

Response (201):
{
  "success": true,
  "data": {
    "society": { "id": "new-society-uuid", "name": "Sunrise Apartments", "status": "onboarding" },
    "admin_user": { "id": "new-user-uuid", "email": "priya@sunrise.in" },
    "message": "Society onboarded. Admin credentials sent via email."
  }
}
```
**Backend logic:**
1. Create society record
2. Create user account for admin (or link existing user)
3. Create `user_roles` entry with `role=admin` and `society_id`
4. Send welcome email with login credentials
5. Generate default billing config

#### `PUT /platform/societies/:societyId`
Update society status, plan, or details.
```
Request: { "status": "active", "plan": "enterprise" }
Response: { "success": true, "data": { ...updatedSociety } }
```

#### `DELETE /platform/societies/:societyId`
Soft-delete (set status to "suspended") or hard-delete a society.
```
Response: { "success": true, "data": { "message": "Society suspended" } }
```

#### `GET /platform/societies/:societyId/audit`
Activity log for a specific society.
```
Response:
{
  "success": true,
  "data": [
    { "timestamp": "2026-03-15T10:30:00Z", "action": "payment_recorded", "user": "Admin", "details": "Payment ₹3,500 for A101 - Mar 2026" }
  ]
}
```

---

### 2.3 SOCIETY (`/societies/:societyId`)

> **Role required:** `admin` or `resident` of this society

#### `GET /societies/:societyId`
Get society details.
```
Response:
{
  "success": true,
  "data": {
    "id": "society-uuid",
    "name": "Greenview Residency",
    "address": "14, MG Road, Koramangala, Bangalore - 560034",
    "phone": "+91 80 4567 8900",
    "email": "admin@greenviewresidency.in",
    "logo_url": null,
    "total_blocks": 3,
    "blocks": ["A", "B", "C"],
    "floors": [1, 2, 3, 4, 5],
    "config": {
      "late_fee": 100,
      "late_fee_type": "per_week",
      "receipt_prefix": "GR",
      "billing_day": 1,
      "grace_period_days": 10,
      "financial_year_start": "April"
    },
    "payment_gateway": {
      "provider": "razorpay",
      "merchant_id": "xxx",
      "key_id": "rzp_live_xxx"
    }
  }
}
```

#### `PUT /societies/:societyId`
Update society info. **Admin only.**
```
Request:
{
  "name": "Greenview Residency",
  "address": "Updated address",
  "config": { "late_fee": 200, "late_fee_type": "per_week" },
  "payment_gateway": { "provider": "razorpay", "key_id": "rzp_live_xxx", "key_secret": "encrypted..." }
}
Response: { "success": true, "data": { ...updatedSociety } }
```

---

### 2.4 FLATS (`/societies/:societyId/flats`)

> **Role required:** `admin` for write, `admin`/`resident` for read

#### `GET /societies/:societyId/flats`
```
Query: ?block=A&occupancy=occupied&search=A101&page=1&limit=50

Response:
{
  "success": true,
  "data": [
    {
      "id": "flat-uuid",
      "flat_number": "A101",
      "block": "A",
      "floor": 1,
      "area": 1200,
      "owner_name": "Rahul Sharma",
      "phone": "+91 98765 43210",
      "email": "rahul@example.com",
      "occupancy": "occupied",
      "maintenance_amount": 3500
    }
  ],
  "pagination": { "total": 55, "page": 1, "limit": 50, "pages": 2 }
}
```

#### `POST /societies/:societyId/flats`
**Admin only.** Create a new flat.
```
Request:
{
  "flat_number": "D101",
  "block": "D",
  "floor": 1,
  "area": 1100,
  "owner_name": "New Owner",
  "phone": "+91 98765 00000",
  "email": "owner@example.com",
  "occupancy": "occupied",
  "maintenance_amount": 3200
}
Response (201): { "success": true, "data": { ...createdFlat } }
```

#### `GET /flats/:flatId`
Get single flat with its residents and payment history.
```
Response:
{
  "success": true,
  "data": {
    "flat": { ...flatDetails },
    "residents": [ { ...resident1 }, { ...resident2 } ],
    "payment_history": [ { ...payment1 } ]
  }
}
```

#### `PUT /flats/:flatId`
**Admin only.** Update flat details.
```
Request: { "owner_name": "Updated Name", "maintenance_amount": 4000 }
Response: { "success": true, "data": { ...updatedFlat } }
```

#### `DELETE /flats/:flatId`
**Admin only.** Soft-delete or remove flat.
```
Response: { "success": true, "data": { "message": "Flat deleted" } }
```

---

### 2.5 RESIDENTS (`/societies/:societyId/residents`)

> **Role required:** `admin` for write, `admin`/`resident` for read

#### `GET /societies/:societyId/residents`
```
Query: ?role=Owner&search=Rahul&active=true&block=A&page=1&limit=50

Response:
{
  "success": true,
  "data": [
    {
      "id": "resident-uuid",
      "name": "Rahul Sharma",
      "flat_id": "flat-uuid",
      "flat_number": "A101",
      "block": "A",
      "phone": "+91 98765 43210",
      "email": "rahul@example.com",
      "role": "Owner",
      "active": true,
      "move_in_date": "2022-06-15",
      "user_id": "user-uuid-or-null"
    }
  ],
  "pagination": { "total": 48, "page": 1, "limit": 50, "pages": 1 }
}
```

#### `POST /societies/:societyId/residents`
**Admin only.** Add a resident to a flat.
```
Request:
{
  "flat_id": "flat-uuid",
  "name": "New Resident",
  "phone": "+91 98765 00001",
  "email": "new@example.com",
  "role": "Tenant",
  "move_in_date": "2026-03-01"
}

Response (201): { "success": true, "data": { ...createdResident } }
```
**Backend logic:**
1. Create resident record
2. Update flat occupancy to "occupied" if vacant
3. Optionally create a user account and assign `resident` role in `user_roles`
4. Send invite email with login link

#### `PUT /residents/:residentId`
**Admin only.** Update resident info.
```
Request: { "phone": "new-phone", "active": false }
Response: { "success": true, "data": { ...updatedResident } }
```

#### `DELETE /residents/:residentId`
**Admin only.** Deactivate resident (set `active=false`). Don't hard-delete for audit trail.
```
Response: { "success": true, "data": { "message": "Resident deactivated" } }
```

---

### 2.6 PAYMENTS (`/societies/:societyId/payments`)

> **Role required:** `admin` for write; `admin`/`resident` for read (resident sees only own flat)

#### `GET /societies/:societyId/payments`
```
Query: ?month=Mar&year=2026&status=unpaid&block=A&flat_id=uuid&page=1&limit=50

Response:
{
  "success": true,
  "data": [
    {
      "id": "payment-uuid",
      "flat_id": "flat-uuid",
      "flat_number": "A101",
      "block": "A",
      "owner_name": "Rahul Sharma",
      "month": "Mar",
      "year": 2026,
      "maintenance_amount": 3500,
      "amount_paid": 3500,
      "balance_due": 0,
      "status": "paid",
      "payment_date": "2026-03-05",
      "payment_mode": "UPI",
      "transaction_ref": "TXN123456",
      "remarks": ""
    }
  ],
  "pagination": { "total": 150, "page": 1, "limit": 50, "pages": 3 }
}
```

#### `POST /societies/:societyId/payments`
**Admin only.** Record a manual payment.
```
Request:
{
  "flat_id": "flat-uuid",
  "month": "Mar",
  "year": 2026,
  "amount_paid": 3500,
  "payment_mode": "Cash",
  "payment_date": "2026-03-10",
  "transaction_ref": "",
  "remarks": "Paid in cash at office"
}

Response (201): { "success": true, "data": { ...paymentRecord } }
```
**Backend logic:**
1. Find or create payment record for (flat_id, month, year)
2. Update `amount_paid` (accumulate for partial payments)
3. Recompute `balance_due` and `status`
4. If `balance_due == 0`, set `status = "paid"`
5. If `amount_paid > 0 && balance_due > 0`, set `status = "partial"`

#### `PUT /payments/:paymentId`
**Admin only.** Edit a payment record.
```
Request: { "amount_paid": 2000, "payment_mode": "Cheque", "remarks": "Partial cheque" }
Response: { "success": true, "data": { ...updatedPayment } }
```

#### `POST /societies/:societyId/payments/generate-bills`
**Admin only.** Auto-generate payment records for all occupied flats for a given month.
```
Request: { "month": "Apr", "year": 2026 }

Response (201):
{
  "success": true,
  "data": {
    "generated": 48,
    "skipped": 3,
    "message": "48 bills generated for Apr 2026. 3 vacant flats skipped."
  }
}
```
**Backend logic:**
1. Get all occupied flats for this society
2. For each flat, check if payment record already exists for (month, year)
3. If not, create with `maintenance_amount` from flat, `status=unpaid`, `amount_paid=0`

#### `POST /societies/:societyId/payments/create-order`
Create a payment gateway order for online payment (resident self-pay).
```
Request: { "flat_id": "flat-uuid", "month": "Mar", "year": 2026, "amount": 3500 }

Response:
{
  "success": true,
  "data": {
    "order_id": "order_PxxxxYyyy",
    "gateway_key": "rzp_live_xxx",
    "amount": 350000,
    "currency": "INR",
    "receipt": "GR-A101-MAR-2026"
  }
}
```

#### `POST /webhooks/payment` (No auth — signature verified)
Payment gateway callback webhook.
```
Request (Razorpay):
{
  "razorpay_order_id": "order_PxxxxYyyy",
  "razorpay_payment_id": "pay_Zzzzz",
  "razorpay_signature": "hmac-sha256-signature"
}

Response: { "status": "ok" }
```
**Backend logic:**
1. Verify signature using society's API secret
2. Find payment by `gateway_order_id`
3. Update `amount_paid`, `status`, `payment_date`, `transaction_ref`, `payment_mode="Online"`
4. Idempotency: skip if already processed

#### `GET /societies/:societyId/payments/summary`
Monthly payment summary for collection tracking.
```
Query: ?year=2026

Response:
{
  "success": true,
  "data": [
    {
      "month": "Jan",
      "year": 2026,
      "total_expected": 185000,
      "total_collected": 170000,
      "total_pending": 15000,
      "paid_count": 45,
      "unpaid_count": 2,
      "partial_count": 3,
      "collection_percentage": 92
    }
  ]
}
```

---

### 2.7 EXPENSES (`/societies/:societyId/expenses`)

> **Role required:** `admin` for write; all roles for read

#### `GET /societies/:societyId/expenses`
```
Query: ?category=Cleaning&month=3&year=2026&search=plumber&page=1&limit=50

Response:
{
  "success": true,
  "data": [
    {
      "id": "expense-uuid",
      "date": "2026-03-10",
      "title": "Cleaning - March 2026",
      "category": "Cleaning",
      "vendor": "CleanCo Services",
      "amount": 8500,
      "added_by": "Admin",
      "notes": "",
      "attachment_url": "https://storage.example.com/receipts/exp-123.pdf",
      "has_attachment": true
    }
  ],
  "pagination": { "total": 25, "page": 1, "limit": 50, "pages": 1 }
}
```

#### `POST /societies/:societyId/expenses`
**Admin only.** Create expense. Supports file upload via `multipart/form-data`.
```
Request (multipart/form-data):
  date: "2026-03-15"
  title: "Plumber repair - Block A"
  category: "Repairs"
  vendor: "QuickFix Repairs"
  amount: 12500
  notes: "Fixed leaking pipes in A301, A302"
  attachment: [file binary]

Response (201): { "success": true, "data": { ...createdExpense } }
```

#### `PUT /expenses/:expenseId`
**Admin only.** Update expense.
```
Request: { "amount": 13000, "notes": "Updated after final bill" }
Response: { "success": true, "data": { ...updatedExpense } }
```

#### `DELETE /expenses/:expenseId`
**Admin only.**
```
Response: { "success": true, "data": { "message": "Expense deleted" } }
```

#### `GET /societies/:societyId/expenses/summary`
Category-wise and monthly expense totals.
```
Query: ?year=2026

Response:
{
  "success": true,
  "data": {
    "monthly": [
      { "month": "Jan", "total": 95000 },
      { "month": "Feb", "total": 102000 }
    ],
    "by_category": [
      { "category": "Staff Salary", "amount": 135000 },
      { "category": "Security", "amount": 75000 }
    ],
    "total_ytd": 450000
  }
}
```

---

### 2.8 NOTICES (`/societies/:societyId/notices`)

> **Role required:** `admin` for write; all roles for read

#### `GET /societies/:societyId/notices`
Returns all active notices sorted by pinned first, then by date descending.
```
Query: ?priority=high&pinned=true

Response:
{
  "success": true,
  "data": [
    {
      "id": "notice-uuid",
      "title": "Annual General Meeting",
      "message": "The AGM for FY 2025-26 is scheduled for...",
      "priority": "high",
      "pinned": true,
      "posted_by": "Admin",
      "posted_date": "2026-03-01",
      "expiry_date": "2026-04-16"
    }
  ]
}
```

#### `POST /societies/:societyId/notices`
**Admin only.**
```
Request:
{
  "title": "Water Tank Cleaning",
  "message": "Water supply will be interrupted from 9 AM to 2 PM...",
  "priority": "medium",
  "pinned": true,
  "expiry_date": "2026-03-21"
}
Response (201): { "success": true, "data": { ...createdNotice } }
```

#### `PUT /notices/:noticeId`
**Admin only.**
```
Request: { "pinned": false, "priority": "low" }
Response: { "success": true, "data": { ...updatedNotice } }
```

#### `DELETE /notices/:noticeId`
**Admin only.**
```
Response: { "success": true, "data": { "message": "Notice deleted" } }
```

---

### 2.9 DASHBOARD AGGREGATIONS

#### `GET /societies/:societyId/dashboard`
**Admin dashboard.** Returns all stats in one call.
```
Response:
{
  "success": true,
  "data": {
    "total_flats": 55,
    "occupied_flats": 51,
    "vacant_flats": 4,
    "current_month": {
      "month": "Mar",
      "year": 2026,
      "total_expected": 185000,
      "total_collected": 152000,
      "total_pending": 33000,
      "total_expenses": 98000,
      "net_balance": 54000,
      "paid_count": 42,
      "unpaid_count": 5,
      "partial_count": 4,
      "collection_percentage": 82
    },
    "monthly_collection": [
      { "month": "Jan", "collected": 170000, "expected": 185000, "pending": 15000 }
    ],
    "monthly_expenses": [
      { "month": "Jan", "total": 95000 }
    ],
    "expense_categories": [
      { "category": "Staff Salary", "amount": 45000 }
    ],
    "recent_expenses": [ ...last5expenses ],
    "pending_flats": [ ...unpaidFlatsThisMonth ],
    "recent_notices": [ ...latest4notices ]
  }
}
```

#### `GET /societies/:societyId/resident-dashboard`
**Resident dashboard.** Returns data scoped to the logged-in user's flat.
```
Response:
{
  "success": true,
  "data": {
    "flat": {
      "id": "flat-uuid",
      "flat_number": "A101",
      "block": "A",
      "floor": 1,
      "area": 1200,
      "maintenance_amount": 3500
    },
    "current_payment": {
      "month": "Mar",
      "year": 2026,
      "status": "unpaid",
      "amount_due": 3500,
      "balance_due": 3500
    },
    "payment_history": [ ...last12MonthsPayments ],
    "community_summary": {
      "total_collected_this_month": 152000,
      "total_expenses_this_month": 98000,
      "collection_percentage": 82
    },
    "recent_expenses": [ ...last5communityExpenses ],
    "recent_notices": [ ...latest4notices ]
  }
}
```

#### `GET /societies/:societyId/reports`
**Admin only.** Detailed report data.
```
Query: ?type=collection&month=3&year=2026
       ?type=expense&month=3&year=2026
       ?type=outstanding&year=2026
       ?type=yearly_summary&year=2026

Response varies by type. Collection report:
{
  "success": true,
  "data": {
    "type": "collection",
    "period": { "month": "Mar", "year": 2026 },
    "summary": { "total_expected": 185000, "total_collected": 152000 },
    "details": [
      { "flat_number": "A101", "block": "A", "owner_name": "Rahul", "amount_due": 3500, "amount_paid": 3500, "status": "paid" }
    ]
  }
}
```

---

### 2.10 FILE UPLOAD

#### `POST /upload`
**Admin only.** Upload an attachment (expense receipt, notice image, society logo).
```
Request (multipart/form-data):
  file: [binary]
  type: "expense_receipt" | "notice_image" | "society_logo"

Response:
{
  "success": true,
  "data": {
    "url": "https://storage.example.com/uploads/abc123.pdf",
    "filename": "receipt.pdf",
    "size": 245000,
    "content_type": "application/pdf"
  }
}
```

---

## 3. JWT TOKEN STRUCTURE

### Access Token Payload
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "name": "Rahul Sharma",
  "roles": [
    { "society_id": "society-uuid", "role": "admin" }
  ],
  "iat": 1711000000,
  "exp": 1711003600
}
```
- **Access token:** 1 hour expiry
- **Refresh token:** 7 days expiry

### For super_admin:
```json
{
  "sub": "user-uuid",
  "roles": [{ "society_id": null, "role": "super_admin" }]
}
```

---

## 4. AUTHORIZATION MIDDLEWARE

```
For every request:
1. Extract Bearer token from Authorization header
2. Verify JWT signature and expiry
3. Extract user_id and roles[] from payload
4. For /platform/* routes → require role === "super_admin"
5. For /societies/:societyId/* routes → require user has role for this societyId
6. For write operations (POST/PUT/DELETE) → require role === "admin" or "super_admin"
7. For resident read routes → filter data to their flat_id only
```

### Role Permission Matrix
| Resource | Super Admin | Admin | Resident |
|----------|-------------|-------|----------|
| Platform societies | CRUD | — | — |
| Society settings | CRUD | CRUD (own) | Read (own) |
| Flats | CRUD (any) | CRUD (own society) | Read (own society) |
| Residents | CRUD (any) | CRUD (own society) | Read (own flat) |
| Payments | CRUD (any) | CRUD (own society) | Read (own flat), Pay online |
| Expenses | CRUD (any) | CRUD (own society) | Read (own society) |
| Notices | CRUD (any) | CRUD (own society) | Read (own society) |
| Dashboard | All societies | Own society | Own flat scope |
| Reports | All societies | Own society | — |

---

## 5. PAYMENT GATEWAY INTEGRATION

### Razorpay Flow
```
1. Resident clicks "Pay Now" on frontend
2. Frontend calls POST /societies/:id/payments/create-order
3. Backend uses society's Razorpay credentials to create order via Razorpay API
4. Backend returns { order_id, gateway_key, amount, currency }
5. Frontend opens Razorpay Checkout SDK with these params
6. User completes payment in Razorpay popup
7. Razorpay sends webhook to POST /webhooks/payment
8. Backend verifies HMAC-SHA256 signature
9. Backend updates payment record: status=paid, payment_mode=Online
10. Frontend polls or receives confirmation
```

### Webhook Security
- Verify `X-Razorpay-Signature` header using HMAC-SHA256 with webhook secret
- Idempotency: check `gateway_order_id` already processed
- Log all webhook payloads for debugging

---

## 6. MULTI-TENANCY RULES

1. **Every table** (except `users`, `user_roles`) has `society_id`
2. **Every query** MUST filter by `society_id` from JWT
3. **Middleware** should inject `society_id` check automatically
4. **Super admin** bypasses society filter but still scopes per-society for data endpoints
5. **Never** expose data across societies
6. **Indexes:** Add composite index on `(society_id, ...)` for all tables

---

## 7. EMAIL NOTIFICATIONS (Optional)

| Trigger | Recipient | Template |
|---------|-----------|----------|
| New society onboarded | Society admin | Welcome + credentials |
| Resident invited | Resident | Login link + flat details |
| Bill generated | All residents | Monthly bill reminder |
| Payment received | Resident | Receipt confirmation |
| Payment overdue | Resident | Reminder with late fee info |
| Notice posted | All residents | Notice content |
| Password reset | User | Reset link |

---

## 8. RECOMMENDED TECH STACK

| Concern | Options |
|---------|---------|
| Runtime | Node.js (Express/Fastify/NestJS), Python (FastAPI/Django), Java (Spring Boot), Go (Gin/Echo) |
| Database | PostgreSQL (recommended) |
| ORM | Prisma, Drizzle, TypeORM, SQLAlchemy, GORM |
| Auth | JWT with bcrypt/argon2 password hashing |
| File Storage | AWS S3, Cloudflare R2, MinIO |
| Payment Gateway | Razorpay (India), PhonePe Business |
| Email | Resend, SendGrid, AWS SES |
| Hosting | AWS, GCP, Railway, Render, DigitalOcean |
| Caching | Redis (for session, rate limiting) |

---

## 9. SUGGESTED INDEXES

```sql
CREATE INDEX idx_flats_society ON flats(society_id);
CREATE INDEX idx_residents_society ON residents(society_id);
CREATE INDEX idx_residents_flat ON residents(flat_id);
CREATE INDEX idx_payments_society_month ON payments(society_id, month, year);
CREATE INDEX idx_payments_flat ON payments(flat_id);
CREATE INDEX idx_payments_status ON payments(society_id, status);
CREATE INDEX idx_expenses_society_date ON expenses(society_id, date);
CREATE INDEX idx_expenses_category ON expenses(society_id, category);
CREATE INDEX idx_notices_society ON notices(society_id);
CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_society ON user_roles(society_id);
```

---

## 10. RATE LIMITING

| Endpoint | Limit |
|----------|-------|
| POST /auth/login | 5 requests/minute per IP |
| POST /auth/forgot-password | 3 requests/minute per email |
| POST /webhooks/* | 100 requests/minute per IP |
| All other endpoints | 60 requests/minute per user |

---

## 11. FRONTEND INTEGRATION NOTES

The frontend is built with React + TypeScript + React Query. It uses:

- `src/config/api.ts` → `API_BASE_URL` and `USE_MOCK` flag
- `src/services/api.ts` → Fetch wrapper with JWT interceptor + auto-refresh
- `src/services/*.ts` → Per-module API functions (auth, flats, residents, payments, expenses, notices, dashboard, societies)
- `src/hooks/use*.ts` → React Query hooks that call services

### To connect:
1. Set `VITE_API_BASE_URL` environment variable to your backend URL
2. Set `USE_MOCK = false` in `src/config/api.ts`
3. Ensure API responses match the TypeScript interfaces in `src/data/demo-data.ts` and `src/services/*.ts`
4. CORS: Allow `Content-Type`, `Authorization` headers from frontend origin

### Response field naming:
- Frontend expects **camelCase** (e.g., `flatNumber`, `ownerName`, `amountPaid`)
- If backend uses snake_case, add a response transformer in `src/services/api.ts`
