# Autonomous Inventory Agent — Documentation

## Overview

The **Autonomous Inventory Agent** is a local-first, agentic inventory management system for restaurant wine inventory. It combines deterministic Python calculations with a local LLM (via Ollama) for diagnosis and recommendations. The system monitors stock, detects anomalies, calculates order quantities, routes decisions for human approval, and generates autonomous morning reports.

**Core architecture principle:** Python calculates facts; the LLM explains, compares, and recommends. The model never calculates quantities or invents data.

---

## Application Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit UI (app.py)                 │
│  Dashboard | Morning Report | Agent Control | Q&A       │
│  Scenario  | Data Import   | Supplier Docs | Chaos     │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                    Agent Logic (agent.py)               │
│  ┌─────────┐  ┌──────────┐  ┌──────────────┐           │
│  │ Watchdog│  │ Optimizer│  │ Autonomy     │           │
│  │         │  │          │  │ Rules        │           │
│  └─────────┘  └──────────┘  └──────────────┘           │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LLM Diagnosis + Q&A (Ollama qwen2.5:7b)         │   │
│  │   - Evidence from Python, never from model      │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐   │
│  │ Supplier     │  │ Morning      │  │ Scenario   │   │
│  │ Tools (RO)   │  │ Report       │  │ Simulator  │   │
│  └──────────────┘  └──────────────┘  └────────────┘   │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                 SQLite Database (inventory.db)          │
│  wines, sales, purchases, suppliers, deliveries,        │
│  stock_counts, waste_events, agent_runs, agent_decisions│
│  questions, supplier_docs                               │
└─────────────────────────────────────────────────────────┘
```

---

## Application Pages

### 1. 📊 Dashboard
**Location:** `app.py` — Dashboard page

**What it does:** Displays the current inventory snapshot with computed status indicators for all wines.

**Features:**
- Shows all wines with SKU, name, stock, reorder point, unit cost, lead time, and reliability
- **Status indicators:**
  - 🔴 Below Reorder — current stock is at or below reorder point
  - 🟡 Low — stock is between reorder point and 1.5× reorder point
  - 🟢 OK — stock is healthy
- **Days Remaining** — projected days until stockout based on 30-day sales velocity
- **Stockout Risk** — 🔴 At Risk if days remaining ≤ lead time; otherwise 🟢 Safe
- **Summary metrics:** count of wines below reorder point, waste this month, open purchase orders

**Definitions:**
- **Reorder Point** — minimum stock level that triggers a replenishment recommendation
- **Sales Velocity** — average bottles sold per day over the last 30 days
- **Lead Time** — supplier delivery time in days

---

### 2. 🌅 Morning Report
**Location:** `app.py` — Morning Report page; `agent.py` — `run_morning_report()`

**What it does:** Runs a complete autonomous morning workflow: detects anomalies, queries suppliers, calculates orders, and generates a daily report.

**Workflow:**
1. Loads restaurant data from the database
2. Calculates sales and inventory metrics for all wines
3. Detects anomalies (low stock, unreliable supplier, stockout risk)
4. Queries supplier documents for each affected SKU
5. Calculates order quantities deterministically
6. Applies tiered autonomy rules (auto-approve vs. pending human)
7. Saves run details and decisions to persistent memory
8. Returns a structured report

**Report contents:**
- **Summary:** wines monitored, anomalies found, decisions made, orders auto-approved, tokens used
- **Yesterday:** sales transactions and waste/spoilage events
- **Today:** wines below reorder point, detected issues with supplier comparisons, open purchase orders

**Output fields per issue:**
| Field | Definition |
|-------|-----------|
| Diagnosis | LLM-generated one-sentence explanation of the anomaly |
| Policy | `min_max` or `order_up_to` replenishment policy |
| Service Level | Target fill rate (0.90–0.99) |
| Order Qty | Deterministically calculated bottles to order |
| Est. Cost | `order_quantity × unit_cost` |
| Decision | `auto_approved` (🤖) or `pending_human` (👤) |
| Days Remaining | Projected days until stockout |
| Predicted Stockout | Date when stock will reach zero |
| Supplier Comparison | Top 3 suppliers with price, lead time, reliability |

---

### 3. 🤖 Agent Control
**Location:** `app.py` — Agent Control page; `agent.py` — `detect_anomalies()`, `process_anomaly()`, `run_full_check()`

**What it does:** Manually triggers the agent to scan for anomalies, process each one through the full pipeline, and display results.

**Pipeline (per SKU):**
1. **Watchdog (detect_anomalies):** Flags wines where `current_stock ≤ reorder_point` OR `supplier_reliability ≤ 2`
2. **LLM Diagnosis (call_llm):** Local Ollama model provides diagnosis, policy, service level, and approval flag
3. **Optimizer (calculate_order_quantity):** Python calculates deterministic order quantity using sales-based demand
4. **Autonomy Rules (decide_autonomy):** Routes to `auto_approved` or `pending_human`
5. **Logging:** Saves to `agent_logs` and `agent_decisions` tables

**Autonomy Rules:**
| Condition | Decision |
|-----------|----------|
| `total_cost ≤ $200` AND `reliability ≥ 3` | `auto_approved` (🤖) |
| Otherwise | `pending_human` (👤) |

**Definitions:**
- **Anomaly** — a wine that needs attention (low stock or unreliable supplier)
- **Policy** — replenishment strategy: `min_max` (order to 2× reorder point) or `order_up_to` (order to target stock based on demand + lead time + safety stock)
- **Tokens Used** — Ollama prompt + eval tokens consumed by the LLM call

---

### 4. ❓ Ask a Question
**Location:** `app.py` — Ask a Question page; `agent.py` — `answer_question()`, `build_inventory_evidence()`, `build_order_recommendations()`

**What it does:** Answers open-ended natural-language questions about inventory using the local LLM grounded in precomputed database evidence.

**How it works (separated responsibilities):**

**Step 1 — Python builds deterministic evidence (`build_inventory_evidence`):**
For each wine, computes:
- Current stock, reorder point, unit cost, lead time, reliability
- 30-day sales total and average daily demand
- Estimated days remaining (`stock ÷ avg daily demand`)
- Supplier options (price, lead time, min order, reliability) for all 3 suppliers

**Step 2 — Python builds order recommendations (`build_order_recommendations`):**
Computes recommended order quantities using: `target = demand × (lead_time + 7)`; `quantity = max(0, ceil(target − stock))`

**Step 3 — LLM explains and recommends (`answer_question`):**
Receives the evidence pack as JSON. System prompt prohibits:
- Inventing stock, sales, reorder points, prices, lead times, or discounts
- Changing any number from the evidence
- Claiming an order was placed (only recommend)

**Example questions:**
- "Which wine should I prioritize before the weekend, and what evidence supports that?"
- "Compare the suppliers for Pinot Noir and recommend the best option considering price, delivery time, and reliability."
- "What changed in our inventory risk after the recent sales?"
- "If weekend sales increase by 30%, which wines are most likely to run out?"

**Definitions:**
- **Evidence Pack** — precomputed JSON of all database facts sent to the LLM
- **LLM Used** — boolean flag in calculations indicating whether Ollama responded successfully

---

### 5. 🎭 Scenario Simulator
**Location:** `app.py` — Scenario Simulator page; `agent.py` — `run_scenario()`, `begin_scenario()`, `end_scenario()`

**What it does:** Runs what-if scenarios without mutating live data. Applies simulated events, runs the agent against the simulated state, and compares results.

**How it works:**
1. `begin_scenario()` snapshots all mutable tables (wines, sales, purchases, waste, agent_logs)
2. Events are applied to the live database temporarily
3. Agent runs against the simulated state
4. `end_scenario()` restores all tables from the snapshot, discarding changes

**Event types:**
| Type | Effect |
|------|--------|
| `sale` | Reduces stock by quantity |
| `waste` | Reduces stock and records a waste event |
| `stock_update` | Adjusts stock by delta (positive or negative) |
| `lead_time` | Increases lead time by delta days |

**Example scenarios:**
- Weekend demand increases by 30%
- Supplier delivery delayed by 5 days
- A wine becomes unavailable (stock set to 0)
- Spoilage removes 10 bottles
- Two suppliers change prices

**Definitions:**
- **Scenario Isolation** — guarantee that what-if simulations never permanently alter live inventory data

---

### 6. 📦 Data Import
**Location:** `app.py` — Data Import page; `db.py` — `import_csv()`, `export_table_to_csv()`

**What it does:** Imports historical restaurant data from CSV files and exports tables to CSV.

**Supported import tables:**
| Table | Required Columns | Example |
|-------|-----------------|---------|
| `sales` | `sold_at, sku, quantity, selling_price, source` | `2026-11-20T18:30:00,SKU-001,3,16.00,pos` |
| `purchases` | `ordered_at, sku, quantity, supplier, expected_delivery, unit_cost, status` | `2026-11-20T08:00:00,SKU-004,24,SUP-001,2026-11-23,9.50,ordered` |
| `waste_events` | `occurred_at, sku, quantity, reason, notes` | `2026-11-20T14:00:00,SKU-004,2,spoilage,bottle broke` |
| `suppliers` | `supplier_id, name, website, reliability` | `SUP-001,Vineyard Direct,https://...,4` |

**Definitions:**
- **POS** — Point of Sale source for sales records
- **Open Purchase Order** — a purchase with status `ordered` or `partial` (not yet fully delivered)

---

### 7. 🏭 Supplier Documents
**Location:** `app.py` — Supplier Documents page; `agent.py` — supplier tools; `db.py` — `get_supplier_docs()`, `get_supplier_doc_content()`

**What it does:** Displays read-only supplier catalogs, price lists, and delivery schedules. The agent consults these before making order recommendations.

**Document types:**
| Type | Contents |
|------|----------|
| `catalog` | Products with SKU, name, category, unit cost, min order qty, case size |
| `price_list` | Current prices per SKU with effective dates and volume discounts |
| `delivery_schedule` | Standard/express delivery days, cutoff times, holiday closures |

**Supplier tools (read-only):**
| Tool | Definition |
|------|-----------|
| `search_supplier_catalog()` | Find products in a supplier's catalog |
| `get_supplier_price()` | Look up unit cost for a SKU from a supplier |
| `check_delivery_schedule()` | Get delivery lead times and schedule |
| `check_minimum_order()` | Get minimum order quantity for a SKU |
| `find_alternative_product()` | Find same-category alternatives |
| `compare_suppliers_for_sku()` | Rank all suppliers for a SKU by price, then reliability |

**Suppliers seeded:**
| Supplier | Reliability | Standard Lead Time |
|----------|-------------|-------------------|
| Vineyard Direct (SUP-001) | 4/5 | 3 days |
| Regional Wine Co (SUP-002) | 3/5 | 5 days |
| Global Imports (SUP-003) | 2/5 | 8 days |

---

### 8. ⚡ Chaos Engine
**Location:** `app.py` — Chaos Engine page

**What it does:** Injects disorder into the system to test the agent's resilience and anomaly detection.

**Actions:**
| Action | Effect |
|--------|--------|
| Simulate Weekend Sales | Reduces stock for 2 random wines by 3–8 bottles each |
| Simulate Spoilage | Removes 3 units from a selected wine |
| Inject Supplier Delay | Adds 3 days to lead time for a selected wine |
| Reset Database | Restores all wines to seed values and clears logs/Q&A |

---

## Database Schema

### Core Tables

**`wines`** — current inventory snapshot
| Column | Type | Definition |
|--------|------|-----------|
| sku | TEXT PK | Stock Keeping Unit identifier |
| name | TEXT | Wine name |
| current_stock | INTEGER | Bottles currently on hand |
| reorder_point | INTEGER | Minimum stock before reorder |
| unit_cost | REAL | Cost per bottle |
| lead_time_days | INTEGER | Supplier delivery days |
| supplier_reliability | INTEGER | 1–5 reliability score |

**`sales`** — historical POS sales
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| sold_at | TEXT | ISO timestamp of sale |
| sku | TEXT | Wine SKU |
| quantity | INTEGER | Bottles sold |
| selling_price | REAL | Price per bottle |
| source | TEXT | Default 'pos' |

**`purchases`** — purchase orders to suppliers
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| ordered_at | TEXT | Order timestamp |
| sku | TEXT | Wine SKU |
| quantity | INTEGER | Bottles ordered |
| supplier | TEXT | Supplier name/ID |
| expected_delivery | TEXT | Expected delivery date |
| actual_delivery | TEXT | Actual delivery date |
| unit_cost | REAL | Cost per bottle |
| status | TEXT | 'ordered', 'partial', or 'delivered' |

**`suppliers`** — supplier master data
| Column | Type | Definition |
|--------|------|-----------|
| supplier_id | TEXT PK | Supplier identifier |
| name | TEXT | Supplier company name |
| website | TEXT | Supplier website URL |
| reliability | INTEGER | 1–5 reliability score |

**`waste_events`** — spoilage/breakage/loss
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| occurred_at | TEXT | Event timestamp |
| sku | TEXT | Wine SKU |
| quantity | INTEGER | Bottles wasted |
| reason | TEXT | Reason (spoilage, breakage, etc.) |
| notes | TEXT | Additional notes |

### Memory Tables

**`agent_runs`** — each autonomous run
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| run_at | TEXT | Run timestamp |
| trigger | TEXT | 'scheduled' or 'manual' |
| anomalies_found | INTEGER | Count |
| decisions_made | INTEGER | Count |
| orders_placed | INTEGER | Auto-approved count |
| tokens_used | INTEGER | Total LLM tokens |
| status | TEXT | 'running' or 'completed' |

**`agent_decisions`** — per-SKU decisions within a run
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| run_id | INTEGER FK | References agent_runs |
| sku | TEXT | Wine SKU |
| trigger_reason | TEXT | Why flagged |
| diagnosis | TEXT | LLM diagnosis |
| policy | TEXT | 'min_max' or 'order_up_to' |
| service_level | REAL | Target fill rate |
| order_quantity | INTEGER | Recommended bottles |
| total_cost | REAL | Estimated order cost |
| status | TEXT | 'auto_approved' or 'pending_human' |
| tokens_used | INTEGER | LLM tokens for this decision |
| actual_outcome | TEXT | Recorded after human acts |

**`questions`** — Q&A history
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| asked_at | TEXT | Question timestamp |
| question | TEXT | User's question |
| answer | TEXT | LLM answer |
| sources | TEXT | JSON list of data sources |
| calculations | TEXT | JSON of calculation metadata |

**`supplier_docs`** — read-only supplier documents
| Column | Type | Definition |
|--------|------|-----------|
| id | INTEGER PK | Auto-increment |
| supplier_id | TEXT FK | References suppliers |
| doc_type | TEXT | 'catalog', 'price_list', 'delivery_schedule' |
| title | TEXT | Document title |
| filename | TEXT | Source JSON filename |
| content_json | TEXT | Document content as JSON |

---

## Key Design Principles

1. **Deterministic Python for calculations** — order quantities, demand, days remaining, and stockout dates are all calculated by Python code, never by the LLM.

2. **LLM for explanation only** — the local Ollama model (`qwen2.5:7b`) provides diagnosis, policy recommendations, supplier comparisons, and natural-language answers, but only from precomputed evidence.

3. **Tiered autonomy** — low-cost, high-reliability orders are auto-approved; everything else routes to human approval.

4. **Scenario isolation** — what-if simulations snapshot and restore the database, never mutating live data.

5. **Persistent memory** — all agent runs, decisions, and Q&A interactions are saved to SQLite for audit and learning.

6. **Local-first** — no cloud APIs; everything runs locally including the LLM via Ollama.

---

## Running the Application

```powershell
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Pull model and run Streamlit
cd E:\Qwen_idea\New_idea_wine_inventory\inventory_agent
ollama pull qwen2.5:7b
streamlit run app.py
```

Then open `http://localhost:8502` in your browser.

**React frontend** (separate, port 3001):
```powershell
cd E:\Qwen_idea\New_idea_wine_inventory
npm run dev -- --port 3001
```

---

## Requirements

- Python 3.14+ with: `streamlit`, `ollama`, `pydantic`, `pandas`
- Node.js with: React, Vite, Tailwind CSS, and related frontend packages
- Ollama running locally with `qwen2.5:7b` model pulled
- SQLite (built into Python)

---

## Repository Structure

```
New_idea_wine_inventory/
├── README.md
├── documentation.md          # This file
├── package.json              # React frontend config
├── package-lock.json
├── tsconfig.json
├── vite.config.js
├── .gitignore
├── index.html
├── src/
│   ├── App.tsx               # React frontend
│   ├── main.tsx
│   └── index.css
├── inventory_agent/
│   ├── app.py                # Streamlit UI (8 pages)
│   ├── agent.py              # Core agent logic (811 lines)
│   ├── db.py                 # Database layer (823 lines)
│   ├── test_agent.py         # 15 test suites
│   ├── seed_data.py          # Populates supplier docs + sample history
│   ├── requirements.txt      # streamlit, ollama, pydantic
│   ├── data/                 # Supplier document JSON files (9 files)
│   │   ├── catalog_*.json
│   │   ├── price_*.json
│   │   └── delivery_*.json
│   └── inventory.db          # SQLite database (auto-created)
└── .kilo/                    # Kilo agent configuration
```

All changes are committed to GitHub at `main`.
