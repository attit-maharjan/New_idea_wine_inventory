"""
Autonomous Inventory Agent - Core logic.
Contains: anomaly detection, LLM integration, deterministic optimizer, autonomy rules.
"""

import logging
from math import ceil
from typing import List, Dict, Optional

from pydantic import BaseModel, Field

import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schema for LLM response
# ---------------------------------------------------------------------------

class LLMResponse(BaseModel):
    """Structured response from the LLM."""
    diagnosis: str = Field(description="One-sentence diagnosis of the anomaly")
    chosen_policy: str = Field(description="Either 'min_max' or 'order_up_to'")
    service_level: float = Field(ge=0.90, le=0.99, description="Target service level")
    requires_human_approval: bool = Field(description="Whether human approval is needed")


# ---------------------------------------------------------------------------
# 1. Deterministic Watchdog
# ---------------------------------------------------------------------------

def detect_anomalies() -> List[Dict]:
    """
    Returns list of wine dicts where:
      current_stock <= reorder_point OR supplier_reliability <= 2
    """
    wines = db.get_all_wines()
    anomalies = []
    for wine in wines:
        if (wine["current_stock"] <= wine["reorder_point"] or
                wine["supplier_reliability"] <= 2):
            # Determine trigger reason
            reasons = []
            if wine["current_stock"] <= wine["reorder_point"]:
                reasons.append("low_stock")
            if wine["supplier_reliability"] <= 2:
                reasons.append("unreliable_supplier")
            wine["trigger_reason"] = " + ".join(reasons)
            anomalies.append(wine)
    return anomalies


# ---------------------------------------------------------------------------
# 2. LLM Call via Ollama
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an Inventory Policy Agent. Analyze the anomaly data. Do NOT calculate order quantities. Return STRICT JSON only with these fields:
- diagnosis: string (1 sentence)
- chosen_policy: 'min_max' or 'order_up_to'
- service_level: float between 0.90 and 0.99
- requires_human_approval: boolean (True if unit_cost * estimated_qty > 200 OR supplier_reliability <= 2)"""


def call_llm(wine: Dict) -> Optional[LLMResponse]:
    """
    Call the local Ollama LLM to get a diagnosis and policy recommendation.
    Returns a parsed LLMResponse or None on failure.
    """
    try:
        import ollama
    except ImportError:
        logger.error("ollama package not installed. Run: pip install ollama")
        return None

    user_prompt = (
        f"Anomaly detected for SKU {wine['sku']}. "
        f"Current stock: {wine['current_stock']}. "
        f"Reorder point: {wine['reorder_point']}. "
        f"Unit cost: ${wine['unit_cost']}. "
        f"Lead time: {wine['lead_time_days']} days. "
        f"Supplier reliability: {wine['supplier_reliability']}/5. "
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

        # Extract content
        content = response["message"]["content"]

        # Parse with Pydantic
        parsed = LLMResponse.model_validate_json(content)

        # Count tokens from ollama response metadata
        tokens_used = 0
        if "prompt_eval_count" in response:
            tokens_used += response["prompt_eval_count"]
        if "eval_count" in response:
            tokens_used += response["eval_count"]

        # Attach tokens to the response object for later use
        parsed._tokens_used = tokens_used  # type: ignore

        return parsed

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        # Return a fallback response so the agent can still function
        fallback = LLMResponse(
            diagnosis=f"LLM unavailable ({str(e)[:50]}). Using default policy.",
            chosen_policy="min_max",
            service_level=0.95,
            requires_human_approval=True,
        )
        fallback._tokens_used = 0  # type: ignore
        return fallback


# ---------------------------------------------------------------------------
# 3. Deterministic Optimizer
# ---------------------------------------------------------------------------

def calculate_order_quantity(
    wine: Dict, policy: str, service_level: float
) -> int:
    """
    Deterministic order quantity calculation.
    
    - If policy == 'min_max': order_qty = reorder_point * 2 - current_stock
    - If policy == 'order_up_to':
        avg_daily_demand = reorder_point / 30
        safety_stock = avg_daily_demand * lead_time_days * (1.0 - service_level) * 2
        target = avg_daily_demand * (lead_time_days + 7) + safety_stock
        order_qty = max(0, ceil(target - current_stock))
    """
    current_stock = wine["current_stock"]
    reorder_point = wine["reorder_point"]
    lead_time_days = wine["lead_time_days"]

    if policy == "min_max":
        order_qty = reorder_point * 2 - current_stock
    elif policy == "order_up_to":
        avg_daily_demand = reorder_point / 30.0
        safety_stock = avg_daily_demand * lead_time_days * (1.0 - service_level) * 2
        target = avg_daily_demand * (lead_time_days + 7) + safety_stock
        order_qty = max(0, ceil(target - current_stock))
    else:
        # Default to min_max if unknown policy
        order_qty = reorder_point * 2 - current_stock

    return max(0, order_qty)


# ---------------------------------------------------------------------------
# 4. Tiered Autonomy
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
# 5. Full Agent Pipeline (for a single SKU)
# ---------------------------------------------------------------------------

def process_anomaly(wine: Dict) -> Dict:
    """
    Full pipeline for a single anomalous SKU:
    1. Call LLM for diagnosis
    2. Run optimizer for quantity
    3. Decide autonomy tier
    4. Log result
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

    # Step 2: Deterministic optimizer
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

    # Step 5: Return result
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
    }


# ---------------------------------------------------------------------------
# 6. Batch runner
# ---------------------------------------------------------------------------

def run_full_check() -> List[Dict]:
    """
    Run the full agent check: detect anomalies, process each, return results.
    """
    anomalies = detect_anomalies()
    results = []
    for wine in anomalies:
        result = process_anomaly(wine)
        results.append(result)
    return results
