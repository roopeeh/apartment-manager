# Split Expenses Feature

## Overview

The split expenses feature allows apartment managers to divide expenses across multiple flats. This is useful for shared expenses like lift maintenance, security, or common area repairs.

## Database Schema

### New Table: `expense_splits`

Tracks individual flat allocations for split expenses.

```sql
CREATE TABLE expense_splits (
    id UUID PRIMARY KEY,
    expense_id UUID REFERENCES expenses(id) ON DELETE CASCADE,
    flat_id UUID REFERENCES flats(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
);
```

### Updated Table: `expenses`

Added `split_mode` column to track how the expense was split.

```sql
ALTER TABLE expenses ADD COLUMN split_mode VARCHAR(50);
```

## Split Modes

The frontend supports four split modes:

1. **all_equal**: Divide expense equally among all flats in the society
2. **selected_equal**: Divide expense equally among selected flats
3. **percentage**: Allocate expense by percentage to selected flats
4. **custom_amount**: Specify exact amount for each selected flat

## API Changes

### Create Expense Endpoint

**Endpoint**: `POST /societies/{society_id}/expenses`

**New Form Parameters**:
- `split_mode` (optional): One of "all_equal", "selected_equal", "percentage", "custom_amount"
- `splits` (optional): JSON string containing array of split items

**Example Request**:

```bash
curl -X POST "http://localhost:8000/societies/{society_id}/expenses" \
  -H "Authorization: Bearer {token}" \
  -F "title=Lift Maintenance" \
  -F "category=Lift Maintenance" \
  -F "amount=10000" \
  -F "date=2026-03-27" \
  -F "split_mode=selected_equal" \
  -F 'splits=[{"flat_id":"uuid-1","amount":2500},{"flat_id":"uuid-2","amount":2500},{"flat_id":"uuid-3","amount":2500},{"flat_id":"uuid-4","amount":2500}]'
```

**Response**:

```json
{
  "success": true,
  "data": {
    "id": "expense-uuid",
    "society_id": "society-uuid",
    "date": "2026-03-27",
    "title": "Lift Maintenance",
    "category": "Lift Maintenance",
    "amount": 10000,
    "split_mode": "selected_equal",
    "splits": [
      {
        "id": "split-uuid-1",
        "expense_id": "expense-uuid",
        "flat_id": "uuid-1",
        "amount": 2500,
        "created_at": "2026-03-27T10:00:00Z"
      },
      {
        "id": "split-uuid-2",
        "expense_id": "expense-uuid",
        "flat_id": "uuid-2",
        "amount": 2500,
        "created_at": "2026-03-27T10:00:00Z"
      }
    ],
    "has_attachment": false,
    "created_at": "2026-03-27T10:00:00Z"
  }
}
```

### List Expenses Endpoint

**Endpoint**: `GET /societies/{society_id}/expenses`

The response now includes `split_mode` and `splits` array for expenses that have been split.

**Example Response**:

```json
{
  "success": true,
  "data": [
    {
      "id": "expense-uuid",
      "title": "Lift Maintenance",
      "amount": 10000,
      "split_mode": "selected_equal",
      "splits": [
        {
          "id": "split-uuid-1",
          "flat_id": "flat-uuid-1",
          "amount": 2500
        }
      ]
    }
  ],
  "pagination": {
    "total": 1,
    "page": 1,
    "limit": 50,
    "pages": 1
  }
}
```

## Backend Implementation Details

### Models (`app/models/models.py`)

**Expense Model Updates**:
```python
class Expense(Base):
    # ... existing fields ...
    split_mode = Column(String(50))
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")
```

**New ExpenseSplit Model**:
```python
class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_id = Column(UUID(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"))
    flat_id = Column(UUID(as_uuid=True), ForeignKey("flats.id", ondelete="CASCADE"))
    amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    expense = relationship("Expense", back_populates="splits")
    flat = relationship("Flat")
```

### Schemas (`app/schemas/expense.py`)

**New Schemas**:
```python
class ExpenseSplitItem(BaseModel):
    flat_id: uuid.UUID
    amount: Decimal

class ExpenseSplitOut(BaseModel):
    id: uuid.UUID
    expense_id: uuid.UUID
    flat_id: uuid.UUID
    amount: Decimal
    created_at: datetime
```

**Updated ExpenseOut**:
```python
class ExpenseOut(BaseModel):
    # ... existing fields ...
    split_mode: Optional[str] = None
    splits: List[ExpenseSplitOut] = []
```

### Router (`app/routers/expenses.py`)

The create_expense endpoint now:
1. Accepts `split_mode` and `splits` form parameters
2. Parses the JSON splits data
3. Creates ExpenseSplit records for each flat allocation
4. Uses database flush() before creating splits to get the expense ID

## Frontend Integration

The frontend (`ExpensesPage.tsx`) provides a UI for:
- Toggling split mode on/off
- Selecting split mode (all equal, selected equal, percentage, custom amount)
- Selecting which flats to include
- Entering percentages or custom amounts per flat
- Preview of split allocation before saving
- Validation that splits add up to 100% or total amount

## Migration

**File**: `alembic/versions/003_add_expense_splits.py`

Run migration:
```bash
alembic upgrade head
```

## Use Cases

1. **Lift Maintenance**: Split equally among all flats
2. **Security Guard Salary**: Split equally among occupied flats only
3. **Water Tank Repair**: Split by percentage based on flat size
4. **Common Area Painting**: Custom amounts based on proximity to painted area

## Future Enhancements

- Add ability to view split details in expense list
- Generate flat-wise expense reports
- Auto-calculate maintenance based on split expenses
- Support recurring split expenses
- Export split expense data for accounting

## Testing

Test the feature by:
1. Creating an expense with split mode enabled
2. Verify splits are saved correctly in database
3. Check that list endpoint returns splits
4. Verify split totals match expense amount
5. Test all four split modes
6. Ensure cascade delete works (deleting expense deletes splits)

## Notes

- Splits are optional - expenses can still be created without splitting
- Split amounts are stored as-is from frontend calculations
- Frontend validates that splits add up correctly before submission
- Backend validates JSON structure but trusts frontend calculations
- Splits are eagerly loaded with expenses using `selectinload(Expense.splits)`
