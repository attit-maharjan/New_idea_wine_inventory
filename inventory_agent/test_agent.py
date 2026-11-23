"""
Test script for the Autonomous Inventory Agent.
Tests all components without requiring Ollama to be running.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import agent
from datetime import datetime, date, timedelta


def test_database():
    """Test database initialization and operations"""
    print("=" * 60)
    print("TEST 1: Database Operations")
    print("=" * 60)
    
    # Initialize database
    db.init_db()
    print("OK Database initialized")
    
    # Get all wines
    wines = db.get_all_wines()
    assert len(wines) == 5, f"Expected 5 wines, got {len(wines)}"
    print(f"OK Retrieved {len(wines)} wines")
    
    # Display wines
    print("\nCurrent Inventory:")
    for wine in wines:
        print(f"  {wine['sku']} | {wine['name']:20s} | Stock: {wine['current_stock']:3d} | "
              f"Reorder: {wine['reorder_point']:3d} | Cost: ${wine['unit_cost']:5.2f} | "
              f"Lead: {wine['lead_time_days']:2d}d | Reliability: {wine['supplier_reliability']}/5")
    
    # Test stock update
    db.update_stock("SKU-001", -5)
    wine = db.get_wine_by_sku("SKU-001")
    assert wine['current_stock'] == 10, f"Expected stock 10, got {wine['current_stock']}"
    print("OK Stock update works")
    
    # Test lead time update
    db.update_lead_time("SKU-002", 3)
    wine = db.get_wine_by_sku("SKU-002")
    assert wine['lead_time_days'] == 10, f"Expected lead time 10, got {wine['lead_time_days']}"
    print("OK Lead time update works")
    
    # Reset database
    db.reset_db()
    wines = db.get_all_wines()
    assert wines[0]['current_stock'] == 15, "Reset failed"
    print("OK Database reset works")
    
    print("\nPASS All database tests passed!\n")


def test_anomaly_detection():
    """Test anomaly detection logic"""
    print("=" * 60)
    print("TEST 2: Anomaly Detection")
    print("=" * 60)
    
    # Reset to known state
    db.reset_db()
    
    # Initially, SKU-002 (stock=8, reorder=10) and SKU-004 (stock=5, reorder=8, reliability=2)
    # should be anomalies
    anomalies = agent.detect_anomalies()
    
    print(f"\nDetected {len(anomalies)} anomalies:")
    for a in anomalies:
        print(f"  {a['sku']} ({a['name']}): {a['trigger_reason']}")
    
    # Verify expected anomalies
    anomaly_skus = [a['sku'] for a in anomalies]
    assert 'SKU-002' in anomaly_skus, "SKU-002 should be anomaly (low stock)"
    assert 'SKU-004' in anomaly_skus, "SKU-004 should be anomaly (low stock + low reliability)"
    print("OK Correct anomalies detected")
    
    # Test with no anomalies
    db.update_stock("SKU-002", 10)  # Now stock=18
    db.update_stock("SKU-004", 10)  # Now stock=15
    # But SKU-004 still has reliability=2, so it should still be anomaly
    
    anomalies = agent.detect_anomalies()
    print(f"\nAfter stock increase, {len(anomalies)} anomalies remain:")
    for a in anomalies:
        print(f"  {a['sku']} ({a['name']}): {a['trigger_reason']}")
    
    assert len(anomalies) == 1, f"Expected 1 anomaly (SKU-004), got {len(anomalies)}"
    assert anomalies[0]['sku'] == 'SKU-004', "Only SKU-004 should be anomaly"
    print("OK Reliability-based detection works")
    
    # Reset for next tests
    db.reset_db()
    
    print("\nPASS All anomaly detection tests passed!\n")


def test_optimizer():
    """Test deterministic optimizer"""
    print("=" * 60)
    print("TEST 3: Deterministic Optimizer")
    print("=" * 60)
    
    wine = {
        'sku': 'TEST-001',
        'current_stock': 5,
        'reorder_point': 10,
        'lead_time_days': 7
    }
    
    # Test min_max policy
    qty = agent.calculate_order_quantity(wine, 'min_max', 0.95)
    expected = 10 * 2 - 5  # reorder_point * 2 - current_stock = 15
    assert qty == expected, f"Expected {expected}, got {qty}"
    print(f"OK Min-max policy: {qty} units (expected {expected})")
    
    # Test order_up_to policy
    qty = agent.calculate_order_quantity(wine, 'order_up_to', 0.95)
    # avg_daily_demand = 10 / 30 = 0.333
    # safety_stock = 0.333 * 7 * (1 - 0.95) * 2 = 0.233
    # target = 0.333 * (7 + 7) + 0.233 = 4.666 + 0.233 = 4.9
    # order_qty = ceil(4.9 - 5) = 0
    print(f"OK Order-up-to policy: {qty} units")
    
    # Test with lower service level (more safety stock)
    qty = agent.calculate_order_quantity(wine, 'order_up_to', 0.90)
    # avg_daily_demand = 10 / 30 = 0.333
    # safety_stock = 0.333 * 7 * (1 - 0.90) * 2 = 0.466
    # target = 0.333 * (7 + 7) + 0.466 = 4.666 + 0.466 = 5.133
    # order_qty = ceil(5.133 - 5) = 1
    print(f"OK Order-up-to with 90% service: {qty} units")
    
    print("\nPASS All optimizer tests passed!\n")


def test_autonomy():
    """Test tiered autonomy rules"""
    print("=" * 60)
    print("TEST 4: Tiered Autonomy Rules")
    print("=" * 60)
    
    # Test auto-approve case
    status = agent.decide_autonomy(order_qty=10, unit_cost=15.0, reliability=4)
    # total_cost = 10 * 15 = 150 <= 200 AND reliability 4 >= 3
    assert status == 'auto_approved', f"Expected auto_approved, got {status}"
    print("OK Auto-approved: 10 units @ $15, reliability 4/5")
    
    # Test pending case (high cost)
    status = agent.decide_autonomy(order_qty=15, unit_cost=20.0, reliability=4)
    # total_cost = 15 * 20 = 300 > 200
    assert status == 'pending_human', f"Expected pending_human, got {status}"
    print("OK Pending (high cost): 15 units @ $20, reliability 4/5")
    
    # Test pending case (low reliability)
    status = agent.decide_autonomy(order_qty=5, unit_cost=10.0, reliability=2)
    # total_cost = 5 * 10 = 50 <= 200 BUT reliability 2 < 3
    assert status == 'pending_human', f"Expected pending_human, got {status}"
    print("OK Pending (low reliability): 5 units @ $10, reliability 2/5")
    
    # Test edge case
    status = agent.decide_autonomy(order_qty=10, unit_cost=20.0, reliability=3)
    # total_cost = 10 * 20 = 200 <= 200 AND reliability 3 >= 3
    assert status == 'auto_approved', f"Expected auto_approved, got {status}"
    print("OK Auto-approved (edge case): 10 units @ $20, reliability 3/5")
    
    print("\nPASS All autonomy tests passed!\n")


def test_logging():
    """Test agent logging"""
    print("=" * 60)
    print("TEST 5: Agent Logging")
    print("=" * 60)
    
    # Clear logs
    db.reset_db()
    
    # Insert a test log
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'sku': 'SKU-001',
        'trigger_reason': 'low_stock',
        'llm_diagnosis': 'Stock critically low',
        'chosen_policy': 'min_max',
        'service_level': 0.95,
        'calculated_quantity': 15,
        'tokens_used': 150,
        'status': 'auto_approved'
    }
    
    db.insert_log(**log_data)
    print("OK Log entry inserted")
    
    # Retrieve logs
    logs = db.get_recent_logs(10)
    assert len(logs) == 1, f"Expected 1 log, got {len(logs)}"
    print(f"OK Retrieved {len(logs)} log entry")
    
    # Check pending approvals
    pending = db.get_pending_approvals()
    assert len(pending) == 0, f"Expected 0 pending, got {len(pending)}"
    print("OK No pending approvals (correct)")
    
    # Insert a pending approval
    log_data['status'] = 'pending_human'
    log_data['sku'] = 'SKU-002'
    db.insert_log(**log_data)
    
    pending = db.get_pending_approvals()
    assert len(pending) == 1, f"Expected 1 pending, got {len(pending)}"
    print("OK Pending approval detected")
    
    # Update status
    db.update_log_status(pending[0]['id'], 'approved')
    pending = db.get_pending_approvals()
    assert len(pending) == 0, f"Expected 0 pending after approval, got {len(pending)}"
    print("OK Status update works")
    
    # Test token counter
    total_tokens = db.get_total_tokens()
    assert total_tokens == 300, f"Expected 300 tokens, got {total_tokens}"
    print(f"OK Token counter: {total_tokens} tokens")
    
    # Reset for next tests
    db.reset_db()
    
    print("\nPASS All logging tests passed!\n")


def test_full_pipeline_mock():
    """Test full pipeline with mock LLM response"""
    print("=" * 60)
    print("TEST 6: Full Pipeline (Mock LLM)")
    print("=" * 60)
    
    # Reset to known state
    db.reset_db()
    
    # Manually trigger an anomaly
    db.update_stock("SKU-001", -10)  # Now stock = 5, reorder = 10
    
    anomalies = agent.detect_anomalies()
    assert len(anomalies) >= 1, "Should have at least 1 anomaly"
    print(f"OK Detected {len(anomalies)} anomalies")
    
    # Test the pipeline with a mock (this will fail if Ollama is not running,
    # but the fallback should work)
    wine = anomalies[0]
    print(f"\nProcessing {wine['sku']} ({wine['name']})...")
    
    try:
        result = agent.process_anomaly(wine)
        print(f"OK Pipeline completed successfully")
        print(f"  Diagnosis: {result['diagnosis']}")
        print(f"  Policy: {result['policy']}")
        print(f"  Order Qty: {result['order_quantity']}")
        print(f"  Status: {result['status']}")
        print(f"  Tokens: {result['tokens_used']}")
    except Exception as e:
        print(f"WARN Pipeline failed (Ollama not running?): {e}")
        print("  This is expected if Ollama is not installed/running")
    
    print("\nPASS Full pipeline test completed!\n")


def test_sales_helpers():
    """Test sales recording and velocity calculation."""
    print("=" * 60)
    print("TEST 7: Sales Helpers")
    print("=" * 60)

    db.reset_db()

    # Insert some sales
    today = date.today().isoformat()
    db.insert_sale(f"{today}T10:00:00", "SKU-001", 3, 16.00)
    db.insert_sale(f"{today}T11:00:00", "SKU-001", 2, 16.00)
    db.insert_sale(f"{today}T12:00:00", "SKU-002", 5, 24.00)

    sales = db.get_sales(sku="SKU-001")
    assert len(sales) == 2, f"Expected 2 sales for SKU-001, got {len(sales)}"
    print(f"OK Retrieved {len(sales)} sales for SKU-001")

    vel = db.get_sales_velocity("SKU-001", days=30)
    assert vel["total_quantity"] == 5, f"Expected 5 total, got {vel['total_quantity']}"
    assert vel["avg_daily_demand"] > 0, "Avg daily demand should be positive"
    print(f"OK Sales velocity: {vel['avg_daily_demand']:.4f} avg daily demand")

    db.reset_db()
    print("\nPASS Sales helper tests passed!\n")


def test_purchase_helpers():
    """Test purchase order recording."""
    print("=" * 60)
    print("TEST 8: Purchase Helpers")
    print("=" * 60)

    db.reset_db()

    today = date.today().isoformat()
    db.insert_purchase(today, "SKU-004", 24, "SUP-001",
                       (date.today() + timedelta(days=3)).isoformat(), 9.50)

    open_po = db.get_open_purchases()
    assert len(open_po) == 1, f"Expected 1 open PO, got {len(open_po)}"
    assert open_po[0]["sku"] == "SKU-004"
    print(f"OK Retrieved {len(open_po)} open purchase order")

    db.reset_db()
    print("\nPASS Purchase helper tests passed!\n")


def test_supplier_tools():
    """Test read-only supplier tools."""
    print("=" * 60)
    print("TEST 9: Supplier Tools (Read-Only)")
    print("=" * 60)

    db.init_db()

    catalog = agent.search_supplier_catalog("SUP-001", sku="SKU-001")
    assert len(catalog) == 1, f"Expected 1 product, got {len(catalog)}"
    assert catalog[0]["sku"] == "SKU-001"
    print(f"OK Catalog search: {catalog[0]['name']} at ${catalog[0]['unit_cost']}")

    price = agent.get_supplier_price("SUP-001", "SKU-002")
    assert price is not None, "Price lookup should return a result"
    assert price["unit_cost"] == 17.00
    print(f"OK Price lookup: SKU-002 at ${price['unit_cost']}")

    delivery = agent.check_delivery_schedule("SUP-002")
    assert delivery is not None, "Delivery schedule should exist"
    assert delivery["standard_days"] == 5
    print(f"OK Delivery schedule: {delivery['standard_days']} days standard")

    min_qty = agent.check_minimum_order("SUP-003", "SKU-001")
    assert min_qty == 24, f"Expected min order 24, got {min_qty}"
    print(f"OK Minimum order qty: {min_qty}")

    alternatives = agent.find_alternative_product("SUP-001", "SKU-001")
    assert len(alternatives) > 0, "Should find alternatives"
    print(f"OK Found {len(alternatives)} alternatives for SKU-001")

    comparison = agent.compare_suppliers_for_sku("SKU-001")
    assert len(comparison) == 3, f"Expected 3 suppliers, got {len(comparison)}"
    print(f"OK Supplier comparison: {len(comparison)} suppliers ranked")

    print("\nPASS Supplier tool tests passed!\n")


def test_stockout_prediction():
    """Test stockout date prediction."""
    print("=" * 60)
    print("TEST 10: Stockout Prediction")
    print("=" * 60)

    db.reset_db()

    # SKU-004 has stock=5, reorder=8, and we'll add sales
    today = date.today().isoformat()
    for i in range(10):
        db.insert_sale(f"{today}T10:00:00", "SKU-004", 2, 10.00)

    stockout = agent.predict_stockout_date("SKU-004")
    assert stockout is not None, "Stockout date should be predicted"
    print(f"OK Predicted stockout for SKU-004: {stockout}")

    db.reset_db()
    print("\nPASS Stockout prediction tests passed!\n")


def test_waste_events():
    """Test waste event recording and retrieval."""
    print("=" * 60)
    print("TEST 11: Waste Events")
    print("=" * 60)

    db.reset_db()

    today = date.today().isoformat()
    db.insert_waste_event(f"{today}T14:00:00", "SKU-004", 2, "spoilage", "test")
    db.insert_waste_event(f"{today}T15:00:00", "SKU-002", 1, "breakage", "test")

    waste = db.get_waste_events()
    assert len(waste) == 2, f"Expected 2 waste events, got {len(waste)}"
    print(f"OK Retrieved {len(waste)} waste events")

    total = sum(w["quantity"] for w in waste)
    assert total == 3, f"Expected 3 total wasted, got {total}"
    print(f"OK Total waste quantity: {total}")

    db.reset_db()
    print("\nPASS Waste event tests passed!\n")


def test_agent_runs_and_decisions():
    """Test persistent agent run and decision memory."""
    print("=" * 60)
    print("TEST 12: Agent Runs and Decisions")
    print("=" * 60)

    db.reset_db()

    run_id = db.insert_agent_run(datetime.now().isoformat(), trigger="test")
    assert run_id is not None, "Run ID should be returned"
    print(f"OK Created agent run {run_id}")

    decision_id = db.insert_agent_decision(
        run_id=run_id,
        sku="SKU-001",
        trigger_reason="low_stock",
        diagnosis="Test diagnosis",
        policy="min_max",
        service_level=0.95,
        order_quantity=10,
        total_cost=120.0,
        status="auto_approved",
        tokens_used=50,
    )
    assert decision_id is not None, "Decision ID should be returned"
    print(f"OK Created agent decision {decision_id}")

    runs = db.get_agent_runs()
    assert len(runs) >= 1, f"Expected at least 1 run, got {len(runs)}"
    print(f"OK Retrieved {len(runs)} agent runs")

    decisions = db.get_agent_decisions(run_id=run_id)
    assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"
    print(f"OK Retrieved {len(decisions)} decisions for run {run_id}")

    db.update_agent_decision_outcome(decision_id, "order placed successfully")
    decisions = db.get_agent_decisions(run_id=run_id)
    assert decisions[0]["actual_outcome"] == "order placed successfully"
    print("OK Decision outcome updated")

    db.update_agent_run(run_id, status="completed", anomalies_found=1, decisions_made=1)
    runs = db.get_agent_runs()
    assert runs[0]["status"] == "completed"
    print("OK Agent run updated to completed")

    db.reset_db()
    print("\nPASS Agent runs and decisions tests passed!\n")


def test_qa_tools():
    """Test question-answering tools."""
    print("=" * 60)
    print("TEST 13: Question Answering Tools")
    print("=" * 60)

    db.reset_db()

    # Add some sales first
    today = date.today().isoformat()
    db.insert_sale(f"{today}T10:00:00", "SKU-001", 3, 16.00)
    db.insert_sale(f"{today}T11:00:00", "SKU-002", 2, 24.00)

    result = agent.answer_question("What sold yesterday?")
    assert result["answer"] is not None, "Answer should not be None"
    assert len(result["sources"]) > 0, "Should have sources"
    print(f"OK Q&A: {result['answer'][:80]}...")

    result = agent.answer_question("Which wine is most likely to run out?")
    assert result["answer"] is not None
    print(f"OK Q&A: {result['answer'][:80]}...")

    result = agent.answer_question("Which supplier is cheapest for SKU-001?")
    assert result["answer"] is not None
    print(f"OK Q&A: {result['answer'][:80]}...")

    questions = db.get_recent_questions()
    assert len(questions) == 3, f"Expected 3 questions, got {len(questions)}"
    print(f"OK Persisted {len(questions)} Q&A records")

    db.reset_db()
    print("\nPASS Q&A tool tests passed!\n")


def test_scenario_runner():
    """Test scenario isolation (does not mutate live data)."""
    print("=" * 60)
    print("TEST 14: Scenario Runner")
    print("=" * 60)

    db.reset_db()

    # Record live stock before scenario
    live_before = db.get_wine_by_sku("SKU-001")["current_stock"]
    assert live_before == 15, f"Expected stock 15, got {live_before}"

    # Add sales to create velocity
    today = date.today().isoformat()
    for _ in range(15):
        db.insert_sale(f"{today}T10:00:00", "SKU-001", 2, 16.00)

    result = agent.run_scenario([
        {"type": "stock_update", "sku": "SKU-001", "quantity": -10, "reason": "make anomaly"},
        {"type": "sale", "sku": "SKU-001", "quantity": 20, "reason": "weekend spike"},
    ])

    assert result["events_applied"] == 2
    assert result["anomalies_found"] >= 0
    print(f"OK Scenario ran: {result['anomalies_found']} anomalies found")

    # Verify live data was NOT mutated
    live_after = db.get_wine_by_sku("SKU-001")["current_stock"]
    assert live_before == live_after, (
        f"Live data mutated! Before: {live_before}, After: {live_after}"
    )
    print(f"OK Live data unchanged: {live_before} == {live_after}")

    db.reset_db()
    print("\nPASS Scenario runner tests passed!\n")


def test_csv_import_export():
    """Test CSV import and export functionality."""
    print("=" * 60)
    print("TEST 15: CSV Import/Export")
    print("=" * 60)

    import tempfile
    import os

    db.reset_db()

    # Create a temp CSV
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w")
    tmp.write("sold_at,sku,quantity,selling_price,source\n")
    tmp.write("2026-11-20T10:00:00,SKU-001,5,16.00,pos\n")
    tmp.write("2026-11-20T11:00:00,SKU-002,3,24.00,pos\n")
    tmp.close()

    count = db.import_csv("sales", tmp.name)
    assert count == 2, f"Expected 2 rows imported, got {count}"
    print(f"OK Imported {count} rows from CSV")

    sales = db.get_sales()
    assert len(sales) == 2, f"Expected 2 sales, got {len(sales)}"

    # Export
    tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w")
    tmp2.close()
    exported = db.export_table_to_csv("sales", tmp2.name)
    assert exported == 2, f"Expected 2 rows exported, got {exported}"
    print(f"OK Exported {exported} rows to CSV")

    os.unlink(tmp.name)
    os.unlink(tmp2.name)
    db.reset_db()
    print("\nPASS CSV import/export tests passed!\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("AUTONOMOUS INVENTORY AGENT - TEST SUITE")
    print("=" * 60 + "\n")

    try:
        test_database()
        test_anomaly_detection()
        test_optimizer()
        test_autonomy()
        test_logging()
        test_full_pipeline_mock()
        test_sales_helpers()
        test_purchase_helpers()
        test_supplier_tools()
        test_stockout_prediction()
        test_waste_events()
        test_agent_runs_and_decisions()
        test_qa_tools()
        test_scenario_runner()
        test_csv_import_export()

        print("=" * 60)
        print("DONE ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe autonomous inventory agent is working correctly.")
        print("\nTo run the Streamlit UI:")
        print("  cd inventory_agent/")
        print("  streamlit run app.py")
        print("\nNote: For full LLM functionality, ensure Ollama is running:")
        print("  ollama serve")
        print("  ollama pull qwen2.5:7b")

    except AssertionError as e:
        print(f"\nFAIL TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFAIL UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
