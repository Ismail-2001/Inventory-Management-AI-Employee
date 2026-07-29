# Inventory Agent — Client Demo Script

**Target audience:** US-based ecommerce operations teams, 3PL providers, and enterprise operations leaders  
**Duration:** 15–20 minutes  
**Goal:** Showcase the autonomous pipeline, human-in-the-loop approval, and business value

---

## Pre-Demo Checklist

- [ ] Docker Compose stack is running (`docker compose up -d`)
- [ ] `.env` is configured with demo credentials
- [ ] Demo data seeded (`python3 seed_demo_data.py`)
- [ ] API accessible at `http://localhost:8002`
- [ ] Swagger UI open at `http://localhost:8002/docs`
- [ ] Dashboard open at `http://localhost:5173` (if frontend is running)
- [ ] Slack webhook configured (optional — to show notifications)

## Demo Flow

### Slide 1 — The Problem (2 min)

> "Every ecommerce team knows this story. You open a spreadsheet on Monday morning. 47 SKUs need attention. Some are about to stock out. Some are overstocked. You spend the morning making PO calls to suppliers, manually calculating reorder quantities, and hoping you got the math right."

**Show the cost table from README:**
- Stockouts = 3–5× lost revenue
- Overstock = 30–50% of working capital locked
- Manual PO cycles = 3–5 days

### Slide 2 — The Solution (2 min)

> "Inventory Agent replaces this with one autonomous pipeline: sync → forecast → risk → PO draft → human approval — all running 24/7."

**Show the architecture diagram** (from README or a whiteboard sketch).

### Slide 3 — Live Demo: Step 1 — Run the Sync (4 min)

**Live action:**

```bash
curl -s -X POST http://localhost:8002/api/v1/run-sync \
  -H "X-API-Key: demo-key-2024" | python -m json.tool
```

**Walk through the response:**
- `synced_products: 10` — we synced 10 SKUs from Shopify
- `synced_sales: 384` — 384 sales records pulled from 90 days
- `risk_alerts: 3` — 3 SKUs flagged as stockout risk
- `purchase_orders: 2` — 2 purchase orders drafted automatically
- `thread_id: "a1b2c3..."` — this ID ties everything together

**Emphasize:** "This entire pipeline — sync, forecast, risk detection, PO drafting — completed in seconds. No human touched it."

### Slide 4 — Live Demo: Step 2 — View the POs (3 min)

**Live action in Swagger UI or curl:**

```bash
curl "http://localhost:8002/api/v1/po?status=pending_approval" \
  -H "X-API-Key: demo-key-2024" | python -m json.tool
```

**Highlight:**
- Each PO has a `reasoning_text` — plain English explanation of why it was recommended
- `total_cost` is calculated automatically
- Status is `pending_approval` — it waits for human approval

**Say:** "The AI drafts the PO with a reasoning you can read and trust. You stay in control."

### Slide 5 — Live Demo: Step 3 — Approve a PO (3 min)

**Option A — Dashboard/Swagger:**

```bash
curl -s -X POST http://localhost:8002/api/v1/po/1/approve \
  -H "X-API-Key: demo-key-2024" \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "operations", "quantity": 50}' | python -m json.tool
```

**Option B — Signed Slack Link (show the token URL):**
- Paste the signed URL from the Slack notification into a browser
- Click "Approve" — no login required
- Show the response: `{"status": "approved", "po_id": 1}`

**Say:** "Approval takes one click. You can override the quantity if your supplier MOQ is different. And because the link is signed with HMAC, no one can forge it."

### Slide 6 — Live Demo: Step 4 — What Happened Next (2 min)

**Check the PO status:**

```bash
curl http://localhost:8002/api/v1/po/1 -H "X-API-Key: demo-key-2024" | python -m json.tool
```

**Show:** Status changed from `pending_approval` to `approved`, with `approved_at` timestamp and `approved_by` field.

**Say:** "The PO is now confirmed. The supplier gets notified. And for the rest of the team — Slack gets a confirmation message so everyone knows it's done."

### Slide 7 — The Numbers (2 min)

**Show the metrics endpoint:**

```bash
curl http://localhost:8002/api/v1/metrics -H "X-API-Key: demo-key-2024" | python -m json.tool
```

**Walk through:**
- PO acceptance rate (60% as-is, 27% edited, 13% rejected)
- Forecast error (12.4% mean error)
- Stockout rate (6.7%)

**Say:** "This isn't just automation — it's a feedback loop. Every PO outcome feeds back into the forecast model. The longer you run it, the smarter it gets."

### Close (1 min)

> "The full cycle — sync Shopify, forecast demand, detect risk, draft POs, get approval — runs end-to-end in seconds. Humans stay in the loop where it matters. Everything else runs 24/7."

**CTA:** "The codebase is open-source and production-ready. Let's discuss how this would look for your specific Shopify store."

---

## Demo Data Reference (For Presenter's Eyes Only)

| SKU Code | Title | Stock | Risk |
|---|---|---|---|
| HWD-BT-001 | Wireless Bluetooth Headphones | **5 units** | 🚨 Critical |
| LPT-USB-C-001 | USB-C Laptop Charger 65W | **3 units** | 🚨 Critical |
| CBL-LIGHT-001 | Lightning Cable 6ft | **2 units** | 🚨 Critical |
| PHN-STND-001 | Phone Stand Adjustable | **0 units** | 🚨 Critical (out of stock) |
| HWD-BT-002 | Wireless Headphones (Black) | 120 units | ✅ Healthy |
| HWD-BT-003 | Wireless Headphones (White) | 45 units | ✅ Healthy |

The demo is designed so that the critical SKUs generate risk alerts automatically, which the risk node detects and feeds into the PO draft node. The presenter never needs to manually create alerts.

---

## Fallback: If API is Down

Have a screenshot of a successful response ready:

```json
{
  "status": "ok",
  "synced_products": 10,
  "synced_sales": 384,
  "risk_alerts": 3,
  "purchase_orders": 2,
  "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```
