"""
Autonomous Inventory Agent - Core logic.
Contains: anomaly detection, LLM integration, deterministic optimizer,
autonomy rules, supplier tools, sales-based demand, stockout prediction,
scenario isolation, morning report, and question-answering tools.
"""

import logging
import json
import os
import copy
import smtplib
from email.message import EmailMessage
from math import ceil
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict

import db

logger = logging.getLogger(__name__)

# Editable notification recipients. Change these values later, or override them
# with MORNING_REPORT_EMAIL and SUPPLIER_ORDER_EMAIL environment variables.
MORNING_REPORT_EMAIL = os.getenv("MORNING_REPORT_EMAIL", "im.coffeeblack@gmail.com")
SUPPLIER_ORDER_EMAIL = os.getenv("SUPPLIER_ORDER_EMAIL", "mrhjn.attit@gmail.com")


def send_email(to_address: str, subject: str, body: str) -> Dict:
    """Send an email through SMTP configured by environment variables.

    Required environment variables: SMTP_HOST, SMTP_PORT, SMTP_USERNAME,
    SMTP_PASSWORD, SMTP_FROM. No email is sent when configuration is missing.
    """
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        return {"sent": False, "to": to_address, "error": "Missing SMTP settings: " + ", ".join(missing)}

    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
        return {"sent": True, "to": to_address, "error": None}
    except Exception as exc:
        logger.exception("Email delivery failed")
        return {"sent": False, "to": to_address, "error": str(exc)}


def format_morning_report_email(report: Dict) -> str:
    """Create a compact plain-text morning report email."""
    summary = report["summary"]
    lines = [
        f"Autonomous wine inventory morning report — {report['date']}",
        "",
        f"Wines monitored: {summary['wines_monitored']}",
        f"Issues found: {summary['anomalies_found']}",
        f"Auto-approved recommendations: {summary['orders_auto_approved']}",
        "",
        "Recommendations:",
    ]
    for issue in report["today"]["issues"]:
        lines.append(
            f"- {issue.get('sku')} {issue.get('name')}: "
            f"{issue.get('order_quantity', 0)} units, ${issue.get('total_cost', 0):.2f}, "
            f"status={issue.get('status')}"
        )
    return "\n".join(lines)


def send_morning_report_email(report: Dict) -> Dict:
    """Send the generated morning report to the configured restaurant address."""
    return send_email(
        MORNING_REPORT_EMAIL,
        f"Wine inventory morning report — {report['date']}",
        format_morning_report_email(report),
    )


def send_supplier_order_email(issue: Dict, supplier: Optional[Dict] = None) -> Dict:
    """Send a recommendation notice for an approved supplier order.

    This is a notification only; the current app does not place a real order.
    """
    supplier_name = (supplier or {}).get("supplier_name", "selected supplier")
    body = (
        "The inventory agent approved a supplier order recommendation.\n\n"
        f"Wine: {issue.get('name')} ({issue.get('sku')})\n"
        f"Quantity: {issue.get('order_quantity')}\n"
        f"Estimated cost: ${issue.get('total_cost', 0):.2f}\n"
        f"Supplier: {supplier_name}\n"
        "\nThis message is a recommendation notification. No external order was placed."
    )
    return send_email(
        SUPPLIER_ORDER_EMAIL,
        f"Supplier order recommendation — {issue.get('sku')}",
        body,
    )

# ---------------------------------------------------------------------------
# Scenario isolation
# ---------------------------------------------------------------------------

_SCENARIO_SNAPSHOT: Optional[dict] = None


def begin_scenario() -> None:
    """Snapshot all mutable tables so a scenario can mutate safely.
    Changes are discarded when end_scenario() is called."""
    global _SCENARIO_SNAPSHOT
    _SCENARIO_SNAPSHOT = {
        "wines": db.get_all_wines(),
        "sales": db.get_sales(),
        "purchases": db.get_open_purchases(),
        "waste": db.get_waste_events(),
        "agent_logs": db.get_recent_logs(limit=10000),
    }


def end_scenario() -> None:
    """Restore all mutable tables from the snapshot, discarding scenario changes."""
    global _SCENARIO_SNAPSHOT
    if _SCENARIO_SNAPSHOT is None:
        return

    snap = _SCENARIO_SNAPSHOT
    conn = db.get_connection()
    cursor = conn.cursor()

    # Restore wines
    cursor.execute("DELETE FROM wines")
    for w in snap["wines"]:
        cursor.execute(
            """INSERT INTO wines (sku, name, current_stock, reorder_point,
               unit_cost, lead_time_days, supplier_reliability)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (w["sku"], w["name"], w["current_stock"], w["reorder_point"],
             w["unit_cost"], w["lead_time_days"], w["supplier_reliability"]),
        )

    # Restore sales
    cursor.execute("DELETE FROM sales")
    for s in snap["sales"]:
        cursor.execute(
            """INSERT INTO sales (sold_at, sku, quantity, selling_price, source)
               VALUES (?, ?, ?, ?, ?)""",
            (s["sold_at"], s["sku"], s["quantity"], s["selling_price"],
             s.get("source", "pos")),
        )

    # Restore purchases
    cursor.execute("DELETE FROM purchases")
    for p in snap["purchases"]:
        cursor.execute(
            """INSERT INTO purchases (ordered_at, sku, quantity, supplier,
               expected_delivery, actual_delivery, unit_cost, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["ordered_at"], p["sku"], p["quantity"], p["supplier"],
             p.get("expected_delivery"), p.get("actual_delivery"),
             p.get("unit_cost"), p.get("status", "ordered")),
        )

    # Restore waste events
    cursor.execute("DELETE FROM waste_events")
    for w in snap["waste"]:
        cursor.execute(
            """INSERT INTO waste_events (occurred_at, sku, quantity, reason, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (w["occurred_at"], w["sku"], w["quantity"], w["reason"],
             w.get("notes", "")),
        )

    # Restore agent logs
    cursor.execute("DELETE FROM agent_logs")
    for log in snap["agent_logs"]:
        cursor.execute(
            """INSERT INTO agent_logs
               (timestamp, sku, trigger_reason, llm_diagnosis, chosen_policy,
                service_level, calculated_quantity, tokens_used, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log["timestamp"], log["sku"], log["trigger_reason"],
             log["llm_diagnosis"], log["chosen_policy"], log["service_level"],
             log["calculated_quantity"], log["tokens_used"], log["status"]),
        )

    conn.commit()
    conn.close()
    _SCENARIO_SNAPSHOT = None


def _in_scenario() -> bool:
    return _SCENARIO_SNAPSHOT is not None


# ---------------------------------------------------------------------------
# Pydantic schema for LLM response
# ---------------------------------------------------------------------------

class LLMResponse(BaseModel):
    """Structured response from the LLM."""
    model_config = ConfigDict(populate_by_name=True)

    diagnosis: str = Field(description="One-sentence diagnosis of the anomaly")
    chosen_policy: str = Field(description="Either 'min_max' or 'order_up_to'")
    service_level: float = Field(ge=0.90, le=0.99, description="Target service level")
    requires_human_approval: bool = Field(
        description="Whether human approval is needed", alias="requires_humanApproval"
    )


# ---------------------------------------------------------------------------
# 1. Deterministic Watchdog (anomaly detection)
# ---------------------------------------------------------------------------

def detect_anomalies() -> List[Dict]:
    """
    Returns list of wine dicts where:
      current_stock <= reorder_point OR supplier_reliability <= 2
    """
    wines = db.get_all_wines()
    anomalies = []
    for wine in wines:
        reasons = []
        if wine["current_stock"] <= wine["reorder_point"]:
            reasons.append("low_stock")
        if wine["supplier_reliability"] <= 2:
            reasons.append("unreliable_supplier")
        if reasons:
            wine["trigger_reason"] = " + ".join(reasons)
            # Add sales-based context
            vel = db.get_sales_velocity(wine["sku"], days=30)
            wine["avg_daily_demand"] = vel["avg_daily_demand"]
            wine["sales_30d"] = vel["total_quantity"]
            anomalies.append(wine)
    return anomalies


def detect_all_issues() -> List[Dict]:
    """Broader detection: low stock, unreliable supplier, waste spike, stockout risk."""
    wines = db.get_all_wines()
    issues = []
    for wine in wines:
        reasons = []
        if wine["current_stock"] <= wine["reorder_point"]:
            reasons.append("low_stock")
        if wine["supplier_reliability"] <= 2:
            reasons.append("unreliable_supplier")

        # Stockout risk: projected days of stock remaining
        vel = db.get_sales_velocity(wine["sku"], days=30)
        avg_daily = vel["avg_daily_demand"]
        days_remaining = None
        if avg_daily > 0 and wine["current_stock"] > 0:
            days_remaining = wine["current_stock"] / avg_daily
            if days_remaining <= wine["lead_time_days"]:
                reasons.append("stockout_risk")

        if reasons:
            wine["trigger_reason"] = " + ".join(reasons)
            wine["avg_daily_demand"] = avg_daily
            wine["days_remaining"] = round(days_remaining, 1) if days_remaining else None
            issues.append(wine)
    return issues


# ---------------------------------------------------------------------------
# 2. Sales-based demand (replaces fixed reorder_point/30 estimate)
# ---------------------------------------------------------------------------

def get_sales_based_demand(sku: str, days: int = 30) -> Dict:
    """Return sales-velocity based demand stats for a SKU."""
    return db.get_sales_velocity(sku, days=days)


def predict_stockout_date(sku: str) -> Optional[str]:
    """Predict the date a SKU will stock out based on recent sales velocity."""
    wine = db.get_wine_by_sku(sku)
    if not wine:
        return None
    vel = db.get_sales_velocity(sku, days=30)
    avg_daily = vel["avg_daily_demand"]
    if avg_daily <= 0 or wine["current_stock"] <= 0:
        return None
    days_remaining = wine["current_stock"] / avg_daily
    stockout_date = date.today() + timedelta(days=days_remaining)
    return stockout_date.isoformat()


# ---------------------------------------------------------------------------
# 3. LLM Call via Ollama
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an Inventory Policy Agent. Analyze the anomaly data. Do NOT calculate order quantities. Return STRICT JSON only with these fields:
- diagnosis: string (1 sentence)
- chosen_policy: 'min_max' or 'order_up_to'
- service_level: float between 0.90 and 0.99
- requires_humanApproval: boolean (True if unit_cost * estimated_qty > 200 OR supplier_reliability <= 2)"""


def call_llm(wine: Dict) -> Optional[LLMResponse]:
    """Call the local Ollama LLM to get a diagnosis and policy recommendation."""
    try:
        import ollama
    except ImportError:
        logger.error("ollama package not installed. Run: pip install ollama")
        return None

    user_prompt = (
        f"Anomaly detected for SKU {wine['sku']} ({wine['name']}). "
        f"Current stock: {wine['current_stock']}. "
        f"Reorder point: {wine['reorder_point']}. "
        f"Unit cost: ${wine['unit_cost']}. "
        f"Lead time: {wine['lead_time_days']} days. "
        f"Supplier reliability: {wine['supplier_reliability']}/5. "
        f"Avg daily demand (30d): {wine.get('avg_daily_demand', 0):.2f}. "
        f"Diagnose and recommend policy."
    )

    try:
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
        )

        content = response["message"]["content"]
        parsed = LLMResponse.model_validate_json(content)

        tokens_used = 0
        if "prompt_eval_count" in response:
            tokens_used += response["prompt_eval_count"]
        if "eval_count" in response:
            tokens_used += response["eval_count"]

        parsed._tokens_used = tokens_used  # type: ignore
        return parsed

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        fallback = LLMResponse(
            diagnosis=f"LLM unavailable ({str(e)[:50]}). Using default policy.",
            chosen_policy="min_max",
            service_level=0.95,
            requires_human_approval=True,
        )
        fallback._tokens_used = 0  # type: ignore
        return fallback


# ---------------------------------------------------------------------------
# 4. Supplier tools (read-only)
# ---------------------------------------------------------------------------

def search_supplier_catalog(supplier_id: str, sku: Optional[str] = None) -> List[Dict]:
    """Read-only search of a supplier's product catalog."""
    content = db.get_supplier_doc_content(supplier_id, "catalog")
    if not content:
        return []
    products = content.get("products", [])
    if sku:
        return [p for p in products if p.get("sku") == sku]
    return products


def get_supplier_price(supplier_id: str, sku: str) -> Optional[Dict]:
    """Read-only lookup of a supplier's price for a SKU."""
    content = db.get_supplier_doc_content(supplier_id, "price_list")
    if not content:
        return None
    prices = content.get("prices", [])
    for p in prices:
        if p.get("sku") == sku:
            return p
    return None


def check_delivery_schedule(supplier_id: str) -> Optional[Dict]:
    """Read-only lookup of a supplier's delivery schedule."""
    return db.get_supplier_doc_content(supplier_id, "delivery_schedule")


def check_minimum_order(supplier_id: str, sku: str) -> Optional[int]:
    """Return the minimum order quantity for a SKU from a supplier."""
    content = db.get_supplier_doc_content(supplier_id, "catalog")
    if not content:
        return None
    products = content.get("products", [])
    for p in products:
        if p.get("sku") == sku:
            return p.get("min_order_qty")
    return None


def find_alternative_product(supplier_id: str, sku: str) -> List[Dict]:
    """Find alternative products from a supplier (same category, different SKU)."""
    content = db.get_supplier_doc_content(supplier_id, "catalog")
    if not content:
        return []
    products = content.get("products", [])
    target = next((p for p in products if p.get("sku") == sku), None)
    if not target:
        return []
    category = target.get("category", "")
    return [p for p in products if p.get("category") == category and p.get("sku") != sku]


def compare_suppliers_for_sku(sku: str) -> List[Dict]:
    """Compare price, lead time, and reliability across all suppliers for a SKU."""
    suppliers = db.get_all_suppliers()
    results = []
    for sup in suppliers:
        price_info = get_supplier_price(sup["supplier_id"], sku)
        delivery = check_delivery_schedule(sup["supplier_id"])
        min_qty = check_minimum_order(sup["supplier_id"], sku)
        results.append({
            "supplier_id": sup["supplier_id"],
            "supplier_name": sup["name"],
            "reliability": sup["reliability"],
            "price": price_info.get("unit_cost") if price_info else None,
            "lead_time_days": delivery.get("standard_days") if delivery else None,
            "min_order_qty": min_qty,
            "delivery_days": delivery.get("standard_days") if delivery else None,
        })
    results.sort(key=lambda x: (x["price"] or 999999, -(x["reliability"] or 0)))
    return results


# ---------------------------------------------------------------------------
# 5. Deterministic Optimizer (sales-aware)
# ---------------------------------------------------------------------------

def calculate_order_quantity(
    wine: Dict, policy: str, service_level: float,
    use_sales_demand: bool = True
) -> int:
    """
    Deterministic order quantity calculation.

    - If policy == 'min_max': order_qty = reorder_point * 2 - current_stock
    - If policy == 'order_up_to':
        avg_daily_demand = sales-based (last 30 days) if available, else reorder_point / 30
        safety_stock = avg_daily_demand * lead_time_days * (1.0 - service_level) * 2
        target = avg_daily_demand * (lead_time_days + 7) + safety_stock
        order_qty = max(0, ceil(target - current_stock))
    """
    current_stock = wine["current_stock"]
    reorder_point = wine["reorder_point"]
    lead_time_days = wine["lead_time_days"]

    if use_sales_demand:
        vel = db.get_sales_velocity(wine["sku"], days=30)
        avg_daily_demand = vel["avg_daily_demand"]
        if avg_daily_demand <= 0:
            avg_daily_demand = reorder_point / 30.0
    else:
        avg_daily_demand = reorder_point / 30.0

    if policy == "min_max":
        order_qty = reorder_point * 2 - current_stock
    elif policy == "order_up_to":
        safety_stock = avg_daily_demand * lead_time_days * (1.0 - service_level) * 2
        target = avg_daily_demand * (lead_time_days + 7) + safety_stock
        order_qty = max(0, ceil(target - current_stock))
    else:
        order_qty = reorder_point * 2 - current_stock

    return max(0, order_qty)


# ---------------------------------------------------------------------------
# 6. Tiered Autonomy
# ---------------------------------------------------------------------------

def decide_autonomy(order_qty: int, unit_cost: float, reliability: int) -> str:
    """
    Determine if the order is auto-approved or needs human approval.
    Rules:
      - total_cost <= 200 AND reliability >= 3 → 'auto_approved'
      - Otherwise → 'pending_human'
    """
    total_cost = order_qty * unit_cost
    if total_cost <= 200 and reliability >= 3:
        return "auto_approved"
    else:
        return "pending_human"


# ---------------------------------------------------------------------------
# 7. Full Agent Pipeline (for a single SKU)
# ---------------------------------------------------------------------------

def process_anomaly(wine: Dict, run_id: Optional[int] = None) -> Dict:
    """
    Full pipeline for a single anomalous SKU:
    1. Call LLM for diagnosis
    2. Run optimizer for quantity
    3. Decide autonomy tier
    4. Log to database
    5. Return result dict
    """
    from datetime import datetime

    # Step 1: LLM diagnosis
    llm_result = call_llm(wine)
    if llm_result is None:
        return {
            "sku": wine["sku"],
            "name": wine["name"],
            "error": "LLM call failed completely",
        }

    diagnosis = llm_result.diagnosis
    policy = llm_result.chosen_policy
    service_level = llm_result.service_level
    tokens_used = getattr(llm_result, "_tokens_used", 0)

    # Step 2: Deterministic optimizer (sales-aware)
    order_qty = calculate_order_quantity(wine, policy, service_level)
    total_cost = order_qty * wine["unit_cost"]

    # Step 3: Autonomy decision
    status = decide_autonomy(order_qty, wine["unit_cost"], wine["supplier_reliability"])

    # Step 4: Log to database
    timestamp = datetime.now().isoformat()
    log_id = db.insert_log(
        timestamp=timestamp,
        sku=wine["sku"],
        trigger_reason=wine.get("trigger_reason", "unknown"),
        llm_diagnosis=diagnosis,
        chosen_policy=policy,
        service_level=service_level,
        calculated_quantity=order_qty,
        tokens_used=tokens_used,
        status=status,
    )

    # Step 5: Persistent decision memory
    decision_id = None
    if run_id is not None:
        decision_id = db.insert_agent_decision(
            run_id=run_id,
            sku=wine["sku"],
            trigger_reason=wine.get("trigger_reason", "unknown"),
            diagnosis=diagnosis,
            policy=policy,
            service_level=service_level,
            order_quantity=order_qty,
            total_cost=total_cost,
            status=status,
            tokens_used=tokens_used,
        )

    return {
        "sku": wine["sku"],
        "name": wine["name"],
        "diagnosis": diagnosis,
        "policy": policy,
        "service_level": service_level,
        "order_quantity": order_qty,
        "total_cost": total_cost,
        "tokens_used": tokens_used,
        "status": status,
        "log_id": log_id,
        "decision_id": decision_id,
    }


# ---------------------------------------------------------------------------
# 8. Batch runner
# ---------------------------------------------------------------------------

def run_full_check() -> List[Dict]:
    """Run the full agent check: detect anomalies, process each, return results."""
    anomalies = detect_anomalies()
    results = []
    for wine in anomalies:
        result = process_anomaly(wine)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# 9. Morning report (scheduled autonomous process)
# ---------------------------------------------------------------------------

def run_morning_report(trigger: str = "scheduled") -> Dict:
    """
    Complete morning autonomous workflow:
    1. Load new restaurant data (already in DB from imports)
    2. Calculate sales and inventory metrics
    3. Detect anomalies (low stock, unreliable supplier, stockout risk)
    4. Query supplier documents when needed
    5. Calculate orders deterministically
    6. Generate daily report
    7. Save report and run details
    8. Return report dict
    """
    run_at = datetime.now().isoformat()
    run_id = db.insert_agent_run(run_at=run_at, trigger=trigger)

    wines = db.get_all_wines()
    issues = detect_all_issues()

    # Yesterday's sales summary
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    sales_yesterday = db.get_sales(start_date=yesterday, end_date=yesterday)

    # Waste events yesterday
    waste_yesterday = db.get_waste_events(start_date=yesterday, end_date=yesterday)

    # Open purchase orders
    open_purchases = db.get_open_purchases()

    results = []
    tokens_used_total = 0
    orders_placed = 0

    for wine in issues:
        vel = db.get_sales_velocity(wine["sku"], days=30)
        stockout = predict_stockout_date(wine["sku"])

        # Compare suppliers for this SKU
        supplier_comparison = compare_suppliers_for_sku(wine["sku"])

        # Run the agent pipeline
        result = process_anomaly(wine, run_id=run_id)
        if "error" not in result:
            tokens_used_total += result.get("tokens_used", 0)
            if result["status"] == "auto_approved":
                orders_placed += 1

        result["sales_30d"] = vel["total_quantity"]
        result["avg_daily_demand"] = round(vel["avg_daily_demand"], 2)
        result["predicted_stockout"] = stockout
        result["days_remaining"] = round(
            wine["current_stock"] / vel["avg_daily_demand"], 1
        ) if vel["avg_daily_demand"] > 0 else None
        result["supplier_comparison"] = supplier_comparison[:3]  # top 3
        results.append(result)

    # Build report
    report = {
        "run_id": run_id,
        "run_at": run_at,
        "date": date.today().isoformat(),
        "summary": {
            "wines_monitored": len(wines),
            "anomalies_found": len(issues),
            "decisions_made": len(results),
            "orders_auto_approved": orders_placed,
            "tokens_used": tokens_used_total,
        },
        "yesterday": {
            "sales": sales_yesterday,
            "waste": waste_yesterday,
        },
        "today": {
            "wines_below_reorder": [
                w for w in wines if w["current_stock"] <= w["reorder_point"]
            ],
            "issues": results,
            "open_purchases": open_purchases,
        },
    }

    # Update run record
    db.update_agent_run(
        run_id,
        anomalies_found=len(issues),
        decisions_made=len(results),
        orders_placed=orders_placed,
        tokens_used=tokens_used_total,
        status="completed",
    )

    return report


# ---------------------------------------------------------------------------
# 10. Question-answering tools
# ---------------------------------------------------------------------------


def build_inventory_evidence() -> dict:
    """Build a deterministic evidence pack with precomputed facts.
    The LLM explains and recommends from these facts; it never calculates them.
    """
    wines = db.get_all_wines()
    suppliers = db.get_all_suppliers()
    evidence = []

    for wine in wines:
        velocity = db.get_sales_velocity(wine["sku"], days=30)
        avg_daily = velocity["avg_daily_demand"]

        if avg_daily > 0:
            days_remaining = wine["current_stock"] / avg_daily
        else:
            days_remaining = None

        supplier_options = compare_suppliers_for_sku(wine["sku"])

        evidence.append({
            "sku": wine["sku"],
            "name": wine["name"],
            "current_stock": wine["current_stock"],
            "reorder_point": wine["reorder_point"],
            "unit_cost": wine["unit_cost"],
            "lead_time_days": wine["lead_time_days"],
            "supplier_reliability": wine["supplier_reliability"],
            "sales_last_30_days": velocity["total_quantity"],
            "average_daily_demand": round(avg_daily, 2),
            "estimated_days_remaining": (
                round(days_remaining, 1)
                if days_remaining is not None else None
            ),
            "supplier_options": supplier_options,
        })

    return {
        "inventory_date": datetime.now().isoformat(),
        "wines": evidence,
        "open_purchases": db.get_open_purchases(),
        "waste_events": db.get_waste_events(),
    }


def build_order_recommendations() -> list:
    """Deterministic order quantity recommendations computed by Python.
    The LLM explains and prioritizes these; it never invents quantities.
    """
    evidence = build_inventory_evidence()
    recommendations = []

    for wine in evidence["wines"]:
        demand = wine["average_daily_demand"]
        lead_time = wine["lead_time_days"]
        stock = wine["current_stock"]

        target_stock = demand * (lead_time + 7)
        quantity = max(0, ceil(target_stock - stock))

        if quantity > 0:
            recommendations.append({
                "sku": wine["sku"],
                "name": wine["name"],
                "current_stock": stock,
                "average_daily_demand": demand,
                "lead_time_days": lead_time,
                "recommended_quantity": quantity,
                "reason": (
                    f"{stock} bottles in stock, "
                    f"{demand} bottles sold per day, "
                    f"{lead_time} day supplier lead time"
                ),
                "supplier_options": wine["supplier_options"],
            })

    return recommendations


def answer_question(question: str) -> Dict:
    """
    Answer an open-ended question with the local LLM grounded in current
    inventory, history, supplier documents, and previous Q&A.  Python
    calculates all facts; the LLM explains, compares, and recommends.
    """
    asked_at = datetime.now().isoformat()
    evidence = build_inventory_evidence()
    evidence["order_recommendations"] = build_order_recommendations()
    sources = ["wines", "sales", "purchases", "waste_events", "order_recommendations"]
    calculations = {"evidence_rows": len(evidence["wines"])}
    system_prompt = """You are a restaurant inventory analyst.

Use only the supplied evidence.

Rules:
1. Never invent stock, sales, reorder points, prices, lead times, or discounts.
2. Never change a number from the evidence.
3. Use the precomputed calculations exactly as provided.
4. If the evidence does not contain an answer, say that it is missing.
5. You may rank options and explain recommendations.
6. For every recommendation, mention the SKU and the evidence supporting it.
7. Do not claim that an order was placed. Only recommend an order.
"""
    user_message = (
        "Inventory evidence:\n"
        + json.dumps(evidence, indent=2, default=str)
        + "\n\nUser question:\n"
        + question
    )
    try:
        import ollama
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        answer = response["message"]["content"].strip()
        calculations["llm_used"] = True
    except Exception as exc:
        logger.exception("General Q&A LLM call failed")
        answer = (
            "The general LLM question service is unavailable. Start Ollama and pull "
            "qwen2.5:7b, then try again. Technical detail: " + str(exc)[:160]
        )
        calculations["llm_used"] = False

    # Persist the Q&A
    db.insert_question(
        asked_at=asked_at,
        question=question,
        answer=answer,
        sources=json.dumps(sources),
        calculations=json.dumps(calculations),
    )

    return {
        "question": question,
        "answer": answer,
        "sources": sources,
        "calculations": calculations,
        "asked_at": asked_at,
    }


# ---------------------------------------------------------------------------
# 11. Scenario runner (isolated)
# ---------------------------------------------------------------------------

def run_scenario(events: List[Dict]) -> Dict:
    """
    Run a what-if scenario without mutating live data.
    events: list of dicts with keys: type ('sale'|'waste'|'stock_update'|'lead_time'),
            sku, quantity, reason, etc.
    Returns scenario results.
    """
    # Snapshot live state
    begin_scenario()

    try:
        # Apply simulated events
        for event in events:
            etype = event.get("type")
            sku = event.get("sku")
            if etype == "sale":
                db.update_stock(sku, -abs(event.get("quantity", 0)))
            elif etype == "waste":
                db.update_stock(sku, -abs(event.get("quantity", 0)))
                db.insert_waste_event(
                    occurred_at=datetime.now().isoformat(),
                    sku=sku,
                    quantity=abs(event.get("quantity", 0)),
                    reason=event.get("reason", "simulated"),
                    notes="scenario simulation",
                )
            elif etype == "stock_update":
                delta = event.get("quantity", 0)
                db.update_stock(sku, delta)
            elif etype == "lead_time":
                delta = event.get("delta", 0)
                db.update_lead_time(sku, delta)

        # Run agent against simulated state
        scenario_issues = detect_all_issues()
        scenario_results = []
        for wine in scenario_issues:
            result = process_anomaly(wine)
            scenario_results.append(result)

        scenario_total_cost = sum(r.get("total_cost", 0) for r in scenario_results if "error" not in r)
        scenario_order_qty = sum(r.get("order_quantity", 0) for r in scenario_results if "error" not in r)

    finally:
        end_scenario()

    return {
        "events_applied": len(events),
        "anomalies_found": len(scenario_issues),
        "total_order_quantity": scenario_order_qty,
        "total_estimated_cost": round(scenario_total_cost, 2),
        "results": scenario_results,
    }
