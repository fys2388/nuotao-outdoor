# Creative Studio C13 Integration Test Script

**Purpose:** Verify the complete Creative Studio flow end-to-end

**Pre-requisites:**
- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173` (or similar)
- OpenAI API key configured in backend `.env`
- At least one Product Master exists in the database

---

## Test Flow

### Step 1: Login & Access Creative Studio

1. Navigate to `http://localhost:5173/login`
2. Login with admin credentials
3. Navigate to `http://localhost:5173/creative`
4. **Expected:** Creative Studio page loads with:
   - Service status badge (green = online)
   - Product selection dropdown
   - Creative Briefs list (may be empty)
   - Stats dashboard (runs, assets, approved, cost)

### Step 2: Select Product Master

1. Click on the product selection dropdown
2. Select any product from the list
3. **Expected:** Product ID is selected

### Step 3: Enter Workbench

1. Click "进入 Workbench" button
2. **Expected:** Navigate to `/creative/workbench/{productId}`
   - Overview tab shows production pipeline steps
   - Stats show brief count, run count, asset count, approved count

### Step 4: Create Creative Brief

1. Click "创建 Brief" button (or on Creative Studio landing page)
2. **Expected:** 
   - Brief is created from product data
   - Brief appears in the list with status "DRAFT"
   - Required assets are generated based on product category

### Step 5: Generate Assets

1. On the Assets tab, click "Generate (4 assets)" button
2. **Expected:**
   - Button shows loading state
   - Generation runs are created (status: QUEUED → RUNNING → SUCCEEDED/FAILED)
   - Assets appear in the gallery with preview images
   - Each asset shows: type, status, version, dimensions

### Step 6: AI QC

1. Click "AI QC" button on any asset
2. **Expected:**
   - Button shows loading state
   - QC results are displayed with:
     - Overall score (0-5)
     - Vision analysis flag (⚠ if text-only)
     - Individual check results (Image Integrity, Product Presence, etc.)
     - Recommendation (approve/approve_with_notes/regenerate/reject)
   - Asset status updates to QC_PASSED or REJECTED

### Step 7: Human Review

1. Click "Review" button on a QC_PASSED asset
2. **Expected:**
   - Review modal opens with:
     - Asset preview
     - AI QC summary
     - Warning: "AI QC Passed ≠ Human Approved"
     - Approve/Reject radio buttons
   - Click "Submit Review"
   - **Expected:** Asset status updates to APPROVED or REJECTED

### Step 8: WooCommerce Push

1. Click "Push WC" button on an APPROVED asset
2. **Expected:**
   - Asset is pushed to WooCommerce
   - `wc_pushed_at` timestamp appears
   - `wc_media_id` is displayed
   - Status shows "WC Pushed" badge

### Step 9: Verify Status Separation

1. Check that assets have clearly separated statuses:
   - **QUEUED/RUNNING** = Generation in progress
   - **QC_PASSED** = AI QC passed (NOT human approved)
   - **APPROVED** = Human approved
   - **REJECTED** = Rejected (by AI or human)
   - **WC_PASSED** = Pushed to WooCommerce

### Step 10: Test Error States

1. Try to push an asset that is NOT APPROVED
   - **Expected:** Error message from backend
2. Try to QC an asset with no image
   - **Expected:** Text-only analysis warning shown
3. Navigate to workbench with invalid product ID
   - **Expected:** Error message or empty state

---

## Verification Checklist

| # | Test | Expected | Pass/Fail |
|---|------|----------|-----------|
| 1 | Login & access Creative Studio | Page loads with dashboard | ☐ |
| 2 | Select Product Master | Product dropdown works | ☐ |
| 3 | Enter Workbench | Navigates to workbench | ☐ |
| 4 | Create Brief | Brief created with required assets | ☐ |
| 5 | Generate Assets | Assets generated with previews | ☐ |
| 6 | AI QC | QC results with vision flag | ☐ |
| 7 | Human Review | Approve/Reject works | ☐ |
| 8 | WC Push | Asset pushed to WooCommerce | ☐ |
| 9 | Status Separation | Distinct statuses visible | ☐ |
| 10 | Error States | Proper error handling | ☐ |

---

## Known Issues to Check

1. **Vision Model:** Does AI QC actually use vision model when image is available?
   - Check `vision_analysis_performed` flag in QC results
   - If `false`, image file may not exist or vision model not configured

2. **Image Preview:** Do generated assets show preview images?
   - Check `preview_url` or `storage_key` in asset data
   - Images should be accessible via `/creative/assets/{id}/image`

3. **WC Push Eligibility:** Does the push button only show for APPROVED assets?
   - Backend enforces: APPROVED + QC_PASSED required
   - Frontend should only show button when eligible

---

## API Endpoints Verification

| Endpoint | Method | Expected Status |
|----------|--------|-----------------|
| `/api/v1/creative/status` | GET | 200 |
| `/api/v1/creative/operations` | GET | 200 (only generate = SUPPORTED) |
| `/api/v1/creative/workspace/{id}` | GET | 200 |
| `/api/v1/creative/workspace/{id}/brief` | POST | 201 |
| `/api/v1/creative/briefs/{id}/generate` | POST | 200 |
| `/api/v1/creative/assets/{id}/ai-qc` | POST | 200 |
| `/api/v1/creative/assets/{id}/review` | POST | 200 |
| `/api/v1/creative/assets/{id}/push-to-wc` | POST | 200 |

---

## Test Data

To run tests, ensure at least one product exists:

```sql
INSERT INTO products (name, sku, category, status)
VALUES ('Test Product', 'TEST-001', 'Electronics', 'active');
```

Or use the Product Intake API:

```bash
curl -X POST http://localhost:8000/api/v1/products/intake \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Product", "sku": "TEST-001", "category": "Electronics"}'
```

---

*Generated: 2026-10-01*
*Status: READY_FOR_MANUAL_TESTING*