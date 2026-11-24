"""
Autonomous Inventory Agent Control Room - Streamlit UI
Main entry point. Run with: streamlit run app.py
"""

import sys
import os
import json
import random
import pandas as pd
import streamlit as st
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import agent

# Ensure DB + seed data + supplier docs are initialized
db.init_db()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🍷 Autonomous Inventory Agent",
    page_icon="🍷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "tokens_today" not in st.session_state:
    st.session_state.tokens_today = db.get_total_tokens()

if "last_results" not in st.session_state:
    st.session_state.last_results = []

if "morning_report" not in st.session_state:
    st.session_state.morning_report = None

if "qa_history" not in st.session_state:
    st.session_state.qa_history = []

# ---------------------------------------------------------------------------
# Sidebar - Navigation
# ---------------------------------------------------------------------------
st.sidebar.title("🍷 Inventory Agent")
page = st.sidebar.radio(
    "Navigate",
    [
        "📊 Dashboard",
        "🌅 Morning Report",
        "🤖 Agent Control",
        "❓ Ask a Question",
        "🎭 Scenario Simulator",
        "📦 Data Import",
        "🏭 Supplier Documents",
        "⚡ Chaos Engine",
    ],
)

st.sidebar.divider()
total_tokens = db.get_total_tokens()
st.sidebar.metric("🪙 Total Tokens Used", f"{total_tokens:,}")
st.sidebar.divider()

# ---------------------------------------------------------------------------
# Page: Dashboard
# ---------------------------------------------------------------------------
if page == "📊 Dashboard":
    st.title("📊 Inventory Dashboard")

    wines = db.get_all_wines()
    if wines:
        df = pd.DataFrame(wines)
        df.columns = [
            "SKU", "Name", "Stock", "Reorder Pt", "Unit Cost ($)",
            "Lead Time (days)", "Reliability (1-5)",
        ]

        # Add stock status
        def stock_status(row):
            if row["Stock"] <= row["Reorder Pt"]:
                return "🔴 Below Reorder"
            elif row["Stock"] <= row["Reorder Pt"] * 1.5:
                return "🟡 Low"
            return "🟢 OK"
        df["Status"] = df.apply(stock_status, axis=1)

        # Add days remaining
        def days_remaining(row):
            vel = db.get_sales_velocity(row["SKU"], days=30)
            avg = vel["avg_daily_demand"]
            if avg > 0 and row["Stock"] > 0:
                return round(row["Stock"] / avg, 1)
            return None
        df["Days Remaining"] = df.apply(days_remaining, axis=1)

        # Add stockout risk
        def stockout_risk(row):
            vel = db.get_sales_velocity(row["SKU"], days=30)
            avg = vel["avg_daily_demand"]
            if avg > 0 and row["Stock"] > 0:
                days = row["Stock"] / avg
                if days <= row["Lead Time (days)"]:
                    return "🔴 At Risk"
            return "🟢 Safe"
        df["Stockout Risk"] = df.apply(stockout_risk, axis=1)

        st.dataframe(df, use_container_width=True, hide_index=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            below = sum(1 for w in wines if w["current_stock"] <= w["reorder_point"])
            st.metric("🔴 Below Reorder Point", below)
        with col2:
            waste_month = db.get_waste_events(
                start_date=date.today().replace(day=1).isoformat()
            )
            st.metric("🗑️ Waste This Month", sum(w["quantity"] for w in waste_month))
        with col3:
            open_po = db.get_open_purchases()
            st.metric("📦 Open Purchase Orders", len(open_po))
    else:
        st.warning("No wines in database.")

# ---------------------------------------------------------------------------
# Page: Morning Report
# ---------------------------------------------------------------------------
elif page == "🌅 Morning Report":
    st.title("🌅 Autonomous Morning Report")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("The agent runs autonomously each morning: detects anomalies, "
                   "queries suppliers, calculates orders, and generates this report.")
    with col2:
        if st.button("🔄 Run Morning Report Now", type="primary", use_container_width=True):
            with st.spinner("Agent running morning analysis..."):
                report = agent.run_morning_report(trigger="manual")
                st.session_state.morning_report = report
                st.session_state.tokens_today = db.get_total_tokens()
            st.success("Morning report complete!")

    report = st.session_state.morning_report
    if report:
        st.divider()

        # Summary
        st.subheader("📋 Summary")
        s = report["summary"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Wines Monitored", s["wines_monitored"])
        c2.metric("Anomalies Found", s["anomalies_found"])
        c3.metric("Decisions Made", s["decisions_made"])
        c4.metric("Orders Auto-Approved", s["orders_auto_approved"])
        c5.metric("Tokens Used", s["tokens_used"])

        st.caption(f"Run ID: {report['run_id']} | {report['run_at']}")

        # Yesterday
        st.subheader("📈 Yesterday")
        y = report["yesterday"]
        if y["sales"]:
            df_sales = pd.DataFrame(y["sales"])
            st.write("**Sales:**")
            st.dataframe(df_sales, use_container_width=True, hide_index=True)
        else:
            st.write("No sales recorded yesterday.")
        if y["waste"]:
            df_waste = pd.DataFrame(y["waste"])
            st.write("**Waste / Spoilage:**")
            st.dataframe(df_waste, use_container_width=True, hide_index=True)
        else:
            st.write("No waste events yesterday.")

        # Today - Issues
        st.subheader("⚠️ Issues Detected Today")
        issues = report["today"]["issues"]
        if issues:
            for issue in issues:
                with st.expander(
                    f"{issue['sku']} — {issue['name']} ({issue['trigger_reason']})",
                    expanded=True,
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Diagnosis:** {issue.get('diagnosis', 'N/A')}")
                        st.markdown(f"**Policy:** `{issue.get('policy', 'N/A')}` "
                                    f"@ {issue.get('service_level', 0)*100:.0f}% service level")
                        st.markdown(f"**Avg Daily Demand:** {issue.get('avg_daily_demand', 0):.2f}")
                        st.markdown(f"**Days Remaining:** {issue.get('days_remaining', 'N/A')}")
                        st.markdown(f"**Predicted Stockout:** {issue.get('predicted_stockout', 'N/A')}")
                    with col2:
                        st.markdown(f"**Order Qty:** {issue.get('order_quantity', 0)} units")
                        st.markdown(f"**Est. Cost:** ${issue.get('total_cost', 0):.2f}")
                        status_emoji = "🤖" if issue.get("status") == "auto_approved" else "👤"
                        st.markdown(f"**{status_emoji} Decision:** {issue.get('status', 'N/A')}")
                        st.markdown(f"**Tokens:** {issue.get('tokens_used', 0)}")

                    # Supplier comparison
                    sup_comp = issue.get("supplier_comparison", [])
                    if sup_comp:
                        st.markdown("**Supplier Comparison:**")
                        df_sup = pd.DataFrame(sup_comp)
                        st.dataframe(df_sup, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No issues detected. System stable.")

        # Open purchases
        st.subheader("📦 Open Purchase Orders")
        open_po = report["today"]["open_purchases"]
        if open_po:
            df_po = pd.DataFrame(open_po)
            st.dataframe(df_po, use_container_width=True, hide_index=True)
        else:
            st.write("No open purchase orders.")

    else:
        st.info("Click 'Run Morning Report Now' to generate the first autonomous report.")

# ---------------------------------------------------------------------------
# Page: Agent Control
# ---------------------------------------------------------------------------
elif page == "🤖 Agent Control":
    st.title("🤖 Autonomous Agent Control")

    if st.button("🔄 Run Agent Check", type="primary", use_container_width=True):
        with st.spinner("Agent scanning for anomalies..."):
            anomalies = agent.detect_anomalies()
        if not anomalies:
            st.success("✅ System stable. Agent slept. 0 tokens used.")
            st.session_state.last_results = []
        else:
            st.info(f"⚠️ {len(anomalies)} anomaly/ies detected. Agent engaging...")
            results = []
            progress = st.progress(0)
            for i, wine in enumerate(anomalies):
                with st.spinner(f"Processing {wine['sku']} ({wine['name']})..."):
                    result = agent.process_anomaly(wine)
                    results.append(result)
                progress.progress((i + 1) / len(anomalies))
            progress.empty()
            st.session_state.last_results = results

    if st.session_state.last_results:
        st.markdown("---")
        st.subheader("📋 Agent Results")
        for result in st.session_state.last_results:
            if "error" in result:
                st.error(f"**{result['sku']}**: {result['error']}")
                continue
            with st.expander(
                f"{'✅' if result['status'] == 'auto_approved' else '⏳'} "
                f"{result['sku']} — {result['name']}",
                expanded=True,
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Diagnosis:** {result['diagnosis']}")
                    st.markdown(f"**Policy:** `{result['policy']}` "
                                f"@ {result['service_level']*100:.0f}%")
                    st.markdown(f"**Order Qty:** {result['order_quantity']} units "
                                f"(${result['total_cost']:.2f})")
                with col2:
                    status_emoji = "🤖" if result["status"] == "auto_approved" else "👤"
                    st.markdown(f"**{status_emoji} Decision:** {result['status']}")
                    st.markdown(f"**Tokens:** {result['tokens_used']}")

    st.markdown("---")
    st.subheader("📜 Recent Agent Runs")
    runs = db.get_agent_runs(limit=10)
    if runs:
        df_runs = pd.DataFrame(runs)
        st.dataframe(df_runs, use_container_width=True, hide_index=True)
    else:
        st.info("No agent runs yet.")

    st.markdown("---")
    st.subheader("⏳ Pending Approvals")
    pending = db.get_pending_approvals()
    if not pending:
        st.success("No pending approvals. All clear!")
    else:
        for log in pending:
            wine = db.get_wine_by_sku(log["sku"])
            wine_name = wine["name"] if wine else "Unknown"
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                with col1:
                    st.markdown(
                        f"**{log['sku']}** — {wine_name} | "
                        f"Qty: {log['calculated_quantity']} | "
                        f"Policy: `{log['chosen_policy']}`"
                    )
                    st.caption(f"Diagnosis: {log['llm_diagnosis']}")
                with col2:
                    st.caption(
                        f"Trigger: {log['trigger_reason']} | "
                        f"Service: {log['service_level']*100:.0f}%"
                    )
                with col3:
                    if st.button("✅ Approve", key=f"approve_{log['id']}"):
                        db.update_log_status(log["id"], "approved")
                        st.rerun()
                with col4:
                    if st.button("❌ Reject", key=f"reject_{log['id']}"):
                        db.update_log_status(log["id"], "rejected")
                        st.rerun()
            st.divider()

# ---------------------------------------------------------------------------
# Page: Ask a Question
# ---------------------------------------------------------------------------
elif page == "❓ Ask a Question":
    st.title("❓ Ask the Agent")

    st.caption("Ask any question about sales, stock, suppliers, waste, purchases, "
               "agent decisions, reports, or what-if analysis. The local LLM answers "
               "from database evidence and supplier documents.")

    question = st.text_input(
        "Your question",
        placeholder="e.g. What sold yesterday? Which wine is most likely to run out?",
    )

    if st.button("Ask", type="primary") and question:
        with st.spinner("Analyzing..."):
            answer = agent.answer_question(question)
            st.session_state.qa_history.insert(0, answer)

    if st.session_state.qa_history:
        st.markdown("---")
        st.subheader("💬 Recent Q&A")
        for qa in st.session_state.qa_history:
            with st.expander(f"Q: {qa['question']}", expanded=False):
                st.markdown(f"**A:** {qa['answer']}")
                if qa["sources"]:
                    st.caption(f"Sources: {', '.join(qa['sources'])}")
                if qa["calculations"]:
                    st.caption(f"Calculations: {json.dumps(qa['calculations'], indent=2)}")

# ---------------------------------------------------------------------------
# Page: Scenario Simulator
# ---------------------------------------------------------------------------
elif page == "🎭 Scenario Simulator":
    st.title("🎭 Scenario Simulator")

    st.caption("Run what-if scenarios without mutating live data. "
               "Apply simulated events, run the agent, and compare results.")

    st.subheader("📋 Simulated Events")

    event_type = st.selectbox(
        "Event Type",
        ["sale", "waste", "stock_update", "lead_time"],
    )
    sku_options = [(w["sku"], w["name"]) for w in db.get_all_wines()]
    sku = st.selectbox("SKU", options=[s[0] for s in sku_options],
                       format_func=lambda x: next(s[1] for s in sku_options if s[0] == x))
    quantity = st.number_input("Quantity", min_value=0, value=0, step=1)
    reason = st.text_input("Reason", value="scenario simulation")
    lead_delta = st.number_input("Lead Time Delta (days)", min_value=0, value=0, step=1)

    if st.button("➕ Add Event", use_container_width=True):
        if "events" not in st.session_state:
            st.session_state.events = []
        event = {
            "type": event_type,
            "sku": sku,
            "quantity": quantity,
            "reason": reason,
        }
        if event_type == "lead_time":
            event["delta"] = lead_delta
        st.session_state.events.append(event)
        st.success(f"Event added: {event_type} for {sku}")

    if st.session_state.get("events"):
        st.write("**Events to apply:**")
        st.json(st.session_state.events)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Run Scenario", type="primary", use_container_width=True):
                with st.spinner("Running scenario simulation..."):
                    result = agent.run_scenario(st.session_state.events)
                    st.session_state.scenario_result = result
                st.success("Scenario complete!")
        with col2:
            if st.button("🗑️ Clear Events", use_container_width=True):
                st.session_state.events = []
                st.rerun()

    if st.session_state.get("scenario_result"):
        st.markdown("---")
        st.subheader("📊 Scenario Results")
        r = st.session_state.scenario_result
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Events Applied", r["events_applied"])
        c2.metric("Anomalies Found", r["anomalies_found"])
        c3.metric("Total Order Qty", r["total_order_quantity"])
        c4.metric("Est. Cost", f"${r['total_estimated_cost']:.2f}")

        for res in r["results"]:
            if "error" in res:
                continue
            with st.expander(f"{res['sku']} — {res['name']}"):
                st.markdown(f"**Order Qty:** {res['order_quantity']} units")
                st.markdown(f"**Cost:** ${res['total_cost']:.2f}")
                st.markdown(f"**Status:** {res['status']}")

# ---------------------------------------------------------------------------
# Page: Data Import
# ---------------------------------------------------------------------------
elif page == "📦 Data Import":
    st.title("📦 Data Import")

    st.caption("Import historical restaurant data from CSV files. "
               "Supported tables: sales, purchases, waste_events, suppliers.")

    import_table = st.selectbox(
        "Import into table",
        ["sales", "purchases", "waste_events", "suppliers"],
    )

    uploaded = st.file_uploader("Choose CSV file", type=["csv"])
    if uploaded is not None:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            count = db.import_csv(import_table, tmp_path)
            st.success(f"✅ Imported {count} rows into {import_table}")
        except Exception as e:
            st.error(f"Import failed: {e}")
        finally:
            os.unlink(tmp_path)

    st.markdown("---")
    st.subheader("📥 Sample CSV Templates")

    st.write("**sales.csv** columns: `sold_at,sku,quantity,selling_price,source`")
    st.code("""sold_at,sku,quantity,selling_price,source
2026-11-20T18:30:00,SKU-001,3,16.00,pos
2026-11-20T19:15:00,SKU-002,2,24.00,pos""")

    st.write("**purchases.csv** columns: `ordered_at,sku,quantity,supplier,expected_delivery,unit_cost,status`")
    st.code("""ordered_at,sku,quantity,supplier,expected_delivery,unit_cost,status
2026-11-20T08:00:00,SKU-004,24,SUP-001,2026-11-23,9.50,ordered""")

    st.write("**waste_events.csv** columns: `occurred_at,sku,quantity,reason,notes`")
    st.code("""occurred_at,sku,quantity,reason,notes
2026-11-20T14:00:00,SKU-004,2,spoilage,bottle broke""")

    st.markdown("---")
    st.subheader("📥 Export")
    export_table = st.selectbox("Export table", ["sales", "purchases", "waste_events", "agent_logs", "wines"])
    if st.button("Export to CSV"):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp_path = tmp.name
        count = db.export_table_to_csv(export_table, tmp_path)
        with open(tmp_path, "rb") as f:
            st.download_button(
                label=f"Download {export_table}.csv ({count} rows)",
                data=f.read(),
                file_name=f"{export_table}.csv",
                mime="text/csv",
            )
        os.unlink(tmp_path)

# ---------------------------------------------------------------------------
# Page: Supplier Documents
# ---------------------------------------------------------------------------
elif page == "🏭 Supplier Documents":
    st.title("🏭 Supplier Documents")

    st.caption("Read-only supplier catalogs, price lists, and delivery schedules. "
               "The agent consults these before making order recommendations.")

    docs = db.get_supplier_docs()
    if docs:
        df_docs = pd.DataFrame(docs)
        st.dataframe(df_docs[["supplier_id", "doc_type", "title", "filename"]],
                     use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📄 Document Content")
        doc_id = st.selectbox(
            "Select document",
            options=[d["id"] for d in docs],
            format_func=lambda x: next(f"{d['supplier_id']} — {d['doc_type']}" for d in docs if d["id"] == x),
        )
        selected = next(d for d in docs if d["id"] == doc_id)
        content = json.loads(selected["content_json"])
        st.json(content)
    else:
        st.info("No supplier documents found. Run seed_data.py to populate.")

# ---------------------------------------------------------------------------
# Page: Chaos Engine
# ---------------------------------------------------------------------------
elif page == "⚡ Chaos Engine":
    st.title("⚡ Chaos Engine")
    st.markdown("*Inject disorder into the system to test the agent.*")

    wines = db.get_all_wines()
    wine_choices = db.get_wine_skus()

    # Simulate Weekend Sales
    st.subheader("🛒 Simulate Weekend Sales")
    if st.button("Run", use_container_width=True, key="chaos_sales"):
        selected = random.sample(wines, min(2, len(wines)))
        for wine in selected:
            reduction = random.randint(3, 8)
            db.update_stock(wine["sku"], -reduction)
        st.success(f"Sales simulated! Reduced stock for {len(selected)} wines.")
        st.rerun()

    # Simulate Spoilage
    st.subheader("🗑️ Simulate Spoilage")
    spoilage_sku = st.selectbox(
        "Target SKU:",
        options=[s[0] for s in wine_choices],
        format_func=lambda x: next(s[1] for s in wine_choices if s[0] == x),
        key="spoilage_select_v2",
    )
    if st.button("Run", use_container_width=True, key="chaos_spoilage"):
        db.update_stock(spoilage_sku, -3)
        st.success(f"3 units of {spoilage_sku} spoiled!")
        st.rerun()

    # Inject Supplier Delay
    st.subheader("🚚 Inject Supplier Delay")
    delay_sku = st.selectbox(
        "Target SKU:",
        options=[s[0] for s in wine_choices],
        format_func=lambda x: next(s[1] for s in wine_choices if s[0] == x),
        key="delay_select_v2",
    )
    if st.button("Run", use_container_width=True, key="chaos_delay"):
        db.update_lead_time(delay_sku, 3)
        st.success(f"Lead time +3 days for {delay_sku}!")
        st.rerun()

    st.divider()
    if st.button("🔄 Reset Database", use_container_width=True, type="secondary"):
        db.reset_db()
        st.session_state.tokens_today = 0
        st.session_state.last_results = []
        st.session_state.morning_report = None
        st.session_state.qa_history = []
        st.session_state.pop("events", None)
        st.session_state.pop("scenario_result", None)
        st.success("Database reset to seed values.")
        st.rerun()
