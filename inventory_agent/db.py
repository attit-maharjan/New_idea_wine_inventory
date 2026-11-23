"""
Database initialization and helpers for the Autonomous Inventory Agent.
Uses SQLite with file: inventory.db

Schema:
- wines            : current inventory snapshot (existing)
- sales            : historical POS sales records
- purchases        : purchase orders to suppliers
- suppliers        : supplier master data
- deliveries       : delivery receipts vs purchase orders
- stock_counts     : physical stock count snapshots
- waste_events     : spoilage / breakage / loss events
- agent_runs       : each autonomous agent run (persistent memory)
- agent_decisions  : individual decisions within a run (outcome memory)
- questions        : Q&A history with sources and calculations
- supplier_docs    : read-only supplier document metadata
"""

import sqlite3
import os
import csv
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

SEED_DATA = [
    ("SKU-001", "Chardonnay", 15, 10, 12.0, 5, 4),
    ("SKU-002", "Pinot Noir", 8, 10, 18.0, 7, 3),
    ("SKU-003", "Cabernet", 20, 12, 22.0, 6, 5),
    ("SKU-004", "Sauvignon Blanc", 5, 8, 10.0, 4, 2),
    ("SKU-005", "Prosecco", 12, 10, 14.0, 5, 4),
]

SUPPLIER_SEED = [
    ("SUP-001", "Vineyard Direct", "https://vineyard-direct.example.com", 4),
    ("SUP-002", "Regional Wine Co", "https://regional-wine.example.com", 3),
    ("SUP-003", "Global Imports", "https://global-imports.example.com", 2),
]

SUPPLIER_DOCS_SEED = [
    ("SUP-001", "catalog", "Vineyard Direct Product Catalog", "catalog_vineyard_direct.json", "{}"),
    ("SUP-001", "price_list", "Vineyard Direct Current Prices", "price_vineyard_direct.json", "{}"),
    ("SUP-001", "delivery_schedule", "Vineyard Direct Delivery Schedule", "delivery_vineyard_direct.json", "{}"),
    ("SUP-002", "catalog", "Regional Wine Co Product Catalog", "catalog_regional_wine.json", "{}"),
    ("SUP-002", "price_list", "Regional Wine Co Current Prices", "price_regional_wine.json", "{}"),
    ("SUP-002", "delivery_schedule", "Regional Wine Co Delivery Schedule", "delivery_regional_wine.json", "{}"),
    ("SUP-003", "catalog", "Global Imports Product Catalog", "catalog_global_imports.json", "{}"),
    ("SUP-003", "price_list", "Global Imports Current Prices", "price_global_imports.json", "{}"),
    ("SUP-003", "delivery_schedule", "Global Imports Delivery Schedule", "delivery_global_imports.json", "{}"),
]


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema and seed data."""
    conn = get_connection()
    cursor = conn.cursor()

    # --- existing tables ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wines (
            sku TEXT PRIMARY KEY,
            name TEXT,
            current_stock INTEGER,
            reorder_point INTEGER,
            unit_cost REAL,
            lead_time_days INTEGER,
            supplier_reliability INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            sku TEXT,
            trigger_reason TEXT,
            llm_diagnosis TEXT,
            chosen_policy TEXT,
            service_level REAL,
            calculated_quantity INTEGER,
            tokens_used INTEGER,
            status TEXT
        )
    """)

    # --- new tables ---

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sold_at TEXT,
            sku TEXT,
            quantity INTEGER,
            selling_price REAL,
            source TEXT DEFAULT 'pos'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordered_at TEXT,
            sku TEXT,
            quantity INTEGER,
            supplier TEXT,
            expected_delivery TEXT,
            actual_delivery TEXT,
            unit_cost REAL,
            status TEXT DEFAULT 'ordered'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            name TEXT,
            website TEXT,
            reliability INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER,
            delivered_at TEXT,
            sku TEXT,
            quantity INTEGER,
            unit_cost REAL,
            notes TEXT,
            FOREIGN KEY (purchase_id) REFERENCES purchases(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            counted_at TEXT,
            sku TEXT,
            counted_quantity INTEGER,
            method TEXT DEFAULT 'manual'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS waste_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT,
            sku TEXT,
            quantity INTEGER,
            reason TEXT,
            notes TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            trigger TEXT DEFAULT 'scheduled',
            anomalies_found INTEGER DEFAULT 0,
            decisions_made INTEGER DEFAULT 0,
            orders_placed INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed',
            report_path TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            sku TEXT,
            trigger_reason TEXT,
            diagnosis TEXT,
            policy TEXT,
            service_level REAL,
            order_quantity INTEGER,
            total_cost REAL,
            status TEXT,
            tokens_used INTEGER,
            approved_at TEXT,
            approved_by TEXT,
            actual_outcome TEXT,
            FOREIGN KEY (run_id) REFERENCES agent_runs(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asked_at TEXT,
            question TEXT,
            answer TEXT,
            sources TEXT,
            calculations TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT,
            doc_type TEXT,
            title TEXT,
            filename TEXT,
            content_json TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        )
    """)

    # Seed wines if empty
    cursor.execute("SELECT COUNT(*) FROM wines")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """INSERT INTO wines (sku, name, current_stock, reorder_point, 
               unit_cost, lead_time_days, supplier_reliability)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            SEED_DATA,
        )

    # Seed suppliers if empty
    cursor.execute("SELECT COUNT(*) FROM suppliers")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """INSERT INTO suppliers (supplier_id, name, website, reliability)
               VALUES (?, ?, ?, ?)""",
            SUPPLIER_SEED,
        )

    # Seed supplier docs if empty
    cursor.execute("SELECT COUNT(*) FROM supplier_docs")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """INSERT INTO supplier_docs (supplier_id, doc_type, title, filename, content_json)
               VALUES (?, ?, ?, ?, ?)""",
            SUPPLIER_DOCS_SEED,
        )

    conn.commit()
    conn.close()


def reset_db() -> None:
    """Reset the database to seed values."""
    conn = get_connection()
    cursor = conn.cursor()

    tables = [
        "agent_decisions", "agent_runs", "questions",
        "waste_events", "stock_counts", "deliveries",
        "purchases", "sales",
    ]
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")

    cursor.execute("DELETE FROM wines")
    cursor.executemany(
        """INSERT INTO wines (sku, name, current_stock, reorder_point, 
           unit_cost, lead_time_days, supplier_reliability)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        SEED_DATA,
    )

    cursor.execute("DELETE FROM agent_logs")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Existing wine helpers (unchanged)
# ---------------------------------------------------------------------------

def get_all_wines() -> List[Dict]:
    """Return all wines as a list of dicts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wines ORDER BY sku")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_wine_by_sku(sku: str) -> Optional[Dict]:
    """Return a single wine by SKU."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wines WHERE sku = ?", (sku,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_stock(sku: str, delta: int) -> None:
    """Update current_stock by delta (can be negative)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE wines SET current_stock = MAX(0, current_stock + ?) WHERE sku = ?",
        (delta, sku),
    )
    conn.commit()
    conn.close()


def update_lead_time(sku: str, delta: int) -> None:
    """Update lead_time_days by delta."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE wines SET lead_time_days = MAX(1, lead_time_days + ?) WHERE sku = ?",
        (delta, sku),
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 20) -> List[Dict]:
    """Return the most recent agent logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM agent_logs ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_approvals() -> List[Dict]:
    """Return all logs with status='pending_human'."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM agent_logs WHERE status = 'pending_human' ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def insert_log(
    timestamp: str,
    sku: str,
    trigger_reason: str,
    llm_diagnosis: str,
    chosen_policy: str,
    service_level: float,
    calculated_quantity: int,
    tokens_used: int,
    status: str,
) -> int:
    """Insert a new agent log entry and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_logs 
           (timestamp, sku, trigger_reason, llm_diagnosis, chosen_policy, 
            service_level, calculated_quantity, tokens_used, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp,
            sku,
            trigger_reason,
            llm_diagnosis,
            chosen_policy,
            service_level,
            calculated_quantity,
            tokens_used,
            status,
        ),
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def update_log_status(log_id: int, new_status: str) -> None:
    """Update the status of a log entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_logs SET status = ? WHERE id = ?", (new_status, log_id)
    )
    conn.commit()
    conn.close()


def get_total_tokens() -> int:
    """Return the sum of all tokens_used from agent_logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(tokens_used), 0) FROM agent_logs")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def get_wine_skus() -> List[Tuple[str, str]]:
    """Return list of (sku, name) tuples for dropdown selection."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, name FROM wines ORDER BY sku")
    rows = cursor.fetchall()
    conn.close()
    return [(row["sku"], row["name"]) for row in rows]


# ---------------------------------------------------------------------------
# NEW: Sales helpers
# ---------------------------------------------------------------------------

def insert_sale(sold_at: str, sku: str, quantity: int,
                selling_price: float, source: str = "pos") -> int:
    """Insert a single sales record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO sales (sold_at, sku, quantity, selling_price, source)
           VALUES (?, ?, ?, ?, ?)""",
        (sold_at, sku, quantity, selling_price, source),
    )
    sale_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sale_id


def get_sales(sku: Optional[str] = None, start_date: Optional[str] = None,
              end_date: Optional[str] = None) -> List[Dict]:
    """Return sales records, optionally filtered by SKU and date range."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM sales WHERE 1=1"
    params: List = []
    if sku:
        query += " AND sku = ?"
        params.append(sku)
    if start_date:
        query += " AND sold_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND sold_at <= ?"
        params.append(end_date)
    query += " ORDER BY sold_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_sales_velocity(sku: str, days: int = 30) -> Dict:
    """Calculate average daily sales quantity for a SKU over the last N days."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT SUM(quantity) as total_qty, COUNT(*) as transaction_count
           FROM sales
           WHERE sku = ? AND sold_at >= date('now', ? || ' days')""",
        (sku, f"-{days}"),
    )
    row = cursor.fetchone()
    conn.close()
    total_qty = row["total_qty"] or 0
    transaction_count = row["transaction_count"] or 0
    avg_daily = total_qty / days if days > 0 else 0
    return {
        "sku": sku,
        "days": days,
        "total_quantity": total_qty,
        "transaction_count": transaction_count,
        "avg_daily_demand": round(avg_daily, 4),
    }


# ---------------------------------------------------------------------------
# NEW: Purchase helpers
# ---------------------------------------------------------------------------

def insert_purchase(ordered_at: str, sku: str, quantity: int, supplier: str,
                    expected_delivery: str, unit_cost: float,
                    status: str = "ordered") -> int:
    """Insert a purchase order."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO purchases (ordered_at, sku, quantity, supplier, 
           expected_delivery, unit_cost, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ordered_at, sku, quantity, supplier, expected_delivery, unit_cost, status),
    )
    purchase_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return purchase_id


def get_open_purchases() -> List[Dict]:
    """Return all purchase orders that are not yet delivered."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM purchases
           WHERE status IN ('ordered', 'partial')
           ORDER BY expected_delivery ASC"""
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# NEW: Supplier helpers
# ---------------------------------------------------------------------------

def get_all_suppliers() -> List[Dict]:
    """Return all suppliers."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY supplier_id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_supplier_by_id(supplier_id: str) -> Optional[Dict]:
    """Return a single supplier by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE supplier_id = ?", (supplier_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# NEW: Supplier document helpers (read-only catalog)
# ---------------------------------------------------------------------------

def get_supplier_docs(supplier_id: Optional[str] = None,
                      doc_type: Optional[str] = None) -> List[Dict]:
    """Return supplier documents, optionally filtered."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM supplier_docs WHERE 1=1"
    params: List = []
    if supplier_id:
        query += " AND supplier_id = ?"
        params.append(supplier_id)
    if doc_type:
        query += " AND doc_type = ?"
        params.append(doc_type)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_supplier_doc_content(supplier_id: str, doc_type: str) -> Optional[Dict]:
    """Return parsed JSON content of a supplier document."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT content_json FROM supplier_docs
           WHERE supplier_id = ? AND doc_type = ?""",
        (supplier_id, doc_type),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        import json
        return json.loads(row["content_json"])
    return None


# ---------------------------------------------------------------------------
# NEW: Waste events
# ---------------------------------------------------------------------------

def insert_waste_event(occurred_at: str, sku: str, quantity: int,
                       reason: str, notes: str = "") -> int:
    """Insert a waste/spoilage event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO waste_events (occurred_at, sku, quantity, reason, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (occurred_at, sku, quantity, reason, notes),
    )
    waste_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return waste_id


def get_waste_events(sku: Optional[str] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> List[Dict]:
    """Return waste events, optionally filtered."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM waste_events WHERE 1=1"
    params: List = []
    if sku:
        query += " AND sku = ?"
        params.append(sku)
    if start_date:
        query += " AND occurred_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND occurred_at <= ?"
        params.append(end_date)
    query += " ORDER BY occurred_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# NEW: Agent runs and decisions (persistent memory)
# ---------------------------------------------------------------------------

def insert_agent_run(run_at: str, trigger: str = "scheduled") -> int:
    """Create a new agent run record and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_runs (run_at, trigger, anomalies_found, decisions_made,
           orders_placed, tokens_used, status)
           VALUES (?, ?, 0, 0, 0, 0, 'running')""",
        (run_at, trigger),
    )
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def update_agent_run(run_id: int, **kwargs) -> None:
    """Update fields on an agent run."""
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    params: List = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(run_id)
    cursor.execute(
        f"UPDATE agent_runs SET {', '.join(fields)} WHERE id = ?", params
    )
    conn.commit()
    conn.close()


def insert_agent_decision(run_id: int, sku: str, trigger_reason: str,
                          diagnosis: str, policy: str, service_level: float,
                          order_quantity: int, total_cost: float, status: str,
                          tokens_used: int) -> int:
    """Insert an agent decision record and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_decisions
           (run_id, sku, trigger_reason, diagnosis, policy, service_level,
            order_quantity, total_cost, status, tokens_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, sku, trigger_reason, diagnosis, policy, service_level,
         order_quantity, total_cost, status, tokens_used),
    )
    decision_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return decision_id


def update_agent_decision_outcome(decision_id: int, outcome: str) -> None:
    """Record the actual outcome of a past decision (for memory/learning)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_decisions SET actual_outcome = ? WHERE id = ?",
        (outcome, decision_id),
    )
    conn.commit()
    conn.close()


def get_agent_runs(limit: int = 10) -> List[Dict]:
    """Return recent agent runs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_agent_decisions(run_id: Optional[int] = None) -> List[Dict]:
    """Return agent decisions, optionally filtered by run."""
    conn = get_connection()
    cursor = conn.cursor()
    if run_id is not None:
        cursor.execute(
            "SELECT * FROM agent_decisions WHERE run_id = ? ORDER BY id DESC",
            (run_id,),
        )
    else:
        cursor.execute("SELECT * FROM agent_decisions ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# NEW: Questions / Q&A memory
# ---------------------------------------------------------------------------

def insert_question(asked_at: str, question: str, answer: str,
                    sources: str, calculations: str) -> int:
    """Save a Q&A interaction for future reference."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO questions (asked_at, question, answer, sources, calculations)
           VALUES (?, ?, ?, ?, ?)""",
        (asked_at, question, answer, sources, calculations),
    )
    q_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return q_id


def get_recent_questions(limit: int = 20) -> List[Dict]:
    """Return recent Q&A history."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM questions ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# NEW: CSV import / export
# ---------------------------------------------------------------------------

def import_csv(table: str, csv_path: str) -> int:
    """Import a CSV file into the given table. Returns number of rows imported."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()
    count = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter out empty keys and None values
            clean_row = {k: v for k, v in row.items() if k is not None and v != ""}
            if not clean_row:
                continue
            columns = ", ".join(clean_row.keys())
            placeholders = ", ".join(["?"] * len(clean_row))
            values = list(clean_row.values())
            cursor.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values
            )
            count += 1

    conn.commit()
    conn.close()
    return count


def export_table_to_csv(table: str, csv_path: str) -> int:
    """Export a table to CSV. Returns number of rows exported."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    return len(rows)


# ---------------------------------------------------------------------------
# NEW: Data directory helpers
# ---------------------------------------------------------------------------

def ensure_data_dir() -> str:
    """Ensure the data directory exists and return its path."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    return DATA_DIR
