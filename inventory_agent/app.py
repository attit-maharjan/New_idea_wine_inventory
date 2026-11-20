"""
Autonomous Inventory Agent Control Room - Streamlit UI
Main entry point. Run with: streamlit run app.py
"""

import sys
import os
import random

# Ensure the current directory is in the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

import db
import agent

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit command)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🍷 Autonomous Inventory Agent",
    page_icon="🍷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Initialize database
# ---------------------------------------------------------------------------
db.init_db()

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "tokens_today" not in st.session_state:
    st.session_state.tokens_today = db.get_total_tokens()

if "last_results" not in st.session_state:
    st.session_state.last_results = []


# ---------------------------------------------------------------------------
# Sidebar - Chaos Engine
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚡ Chaos Engine")
    st.markdown("*Inject disorder into the system to test the agent.*")
    st.divider()

    st.subheader("🎲 Inject Events")

    # --- Simulate Weekend Sales ---
    if st.button("🛒 Simulate Weekend Sales", use_container_width=True):
        wines = db.get_all_wines()
        # Pick 2 random wines
        selected = random.sample(wines, min(2, len(wines)))
        for wine in selected:
            reduction = random.randint(3, 8)
            db.update_stock(wine["sku"], -reduction)
        st.success(f"Sales simulated! Reduced stock for {len(selected)} wines.")
        st.rerun()

    # --- Simulate Spoilage ---
    wine_choices = db.get_wine_skus()
    spoilage_sku = st.selectbox(
        "🗑️ Spoilage target:",
        options=[s[0] for s in wine_choices],
        format_func=lambda x: next(s[1] for s in wine_choices if s[0] == x),
        key="spoilage_select",
    )
    if st.button("💀 Simulate Spoilage", use_container_width=True):
        db.update_stock(spoilage_sku, -3)
        st.success(f"3 units of {spoilage_sku} spoiled!")
        st.rerun()

    # --- Inject Supplier Delay ---
    delay_sku = st.selectbox(
        "🚚 Delay target:",
        options=[s[0] for s in wine_choices],
        format_func=lambda x: next(s[1] for s in wine_choices if s[0] == x),
        key="delay_select",
    )
    if st.button("⏳ Inject Supplier Delay", use_container_width=True):
        db.update_lead_time(delay_sku, 3)
        st.success(f"Lead time +3 days for {delay_sku}!")
        st.rerun()

    st.divider()

    # --- Reset Database ---
    if st.button("🔄 Reset Database", use_container_width=True, type="secondary"):
        db.reset_db()
        st.session_state.tokens_today = 0
        st.session_state.last_results = []
        st.success("Database reset to seed values.")
        st.rerun()

    st.divider()

    # --- Token Counter ---
    total_tokens = db.get_total_tokens()
    st.metric("🪙 Total Tokens Used Today", f"{total_tokens:,}")


# ---------------------------------------------------------------------------
# Main Area
# ---------------------------------------------------------------------------
st.title("🍷 Autonomous Inventory Agent Control Room")
st.markdown(
    "This is **not** a chatbot. An autonomous agent monitors inventory, "
    "detects anomalies, calls a local LLM for diagnosis, runs a deterministic "
    "optimizer, and applies tiered autonomy rules."
)

# ---------------------------------------------------------------------------
# Section 1: Current Inventory
# ---------------------------------------------------------------------------
st.subheader("📦 Current Inventory")
wines = db.get_all_wines()
if wines:
    df_wines = pd.DataFrame(wines)
    df_wines.columns = [
        "SKU", "Name", "Stock", "Reorder Pt", "Unit Cost ($)", "Lead Time (days)", "Reliability (1-5)"
    ]
    st.dataframe(df_wines, use_container_width=True, hide_index=True)
else:
    st.warning("No wines in database.")

# ---------------------------------------------------------------------------
# Section 2: Run Agent Check
# ---------------------------------------------------------------------------
st.subheader("🤖 Autonomous Agent")

if st.button("🔄 Run Autonomous Agent Check", type="primary", use_container_width=True):
    with st.spinner("Agent is scanning for anomalies..."):
        anomalies = agent.detect_anomalies()

    if not anomalies:
        st.success("✅ System stable. Agent slept. 0 tokens used.")
        st.session_state.last_results = []
    else:
        st.info(f"⚠️ {len(anomalies)} anomal{'y' if len(anomalies) == 1 else 'ies'} detected. Agent engaging...")
        results = []
        progress = st.progress(0)
        for i, wine in enumerate(anomalies):
            with st.spinner(f"Processing {wine['sku']} ({wine['name']})..."):
                result = agent.process_anomaly(wine)
                results.append(result)
            progress.progress((i + 1) / len(anomalies))
        progress.empty()
        st.session_state.last_results = results

# ---------------------------------------------------------------------------
# Section 2b: Display Results
# ---------------------------------------------------------------------------
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
                st.markdown(f"**🩺 LLM Diagnosis:** {result['diagnosis']}")
                st.markdown(
                    f"**📐 Chosen Policy:** `{result['policy']}` "
                    f"@ {result['service_level'] * 100:.0f}% service level"
                )
                st.markdown(
                    f"**🧮 Calculated Order:** {result['order_quantity']} units "
                    f"(${result['total_cost']:.2f})"
                )

            with col2:
                status_emoji = "🤖" if result["status"] == "auto_approved" else "👤"
                status_text = (
                    "Auto-Approved" if result["status"] == "auto_approved"
                    else "Pending Human Approval"
                )
                st.markdown(f"**{status_emoji} Autonomy Decision:** {status_text}")
                st.markdown(f"**🪙 Tokens Used:** {result['tokens_used']}")

                if result["status"] == "auto_approved":
                    st.success("Order will be placed automatically.")
                else:
                    st.warning("Awaiting human review.")

# ---------------------------------------------------------------------------
# Section 3: Agent Activity Log
# ---------------------------------------------------------------------------
st.markdown("---")
st.subheader("📜 Agent Activity Log")

logs = db.get_recent_logs(20)
if logs:
    df_logs = pd.DataFrame(logs)
    display_cols = {
        "timestamp": "Time",
        "sku": "SKU",
        "trigger_reason": "Trigger",
        "llm_diagnosis": "Diagnosis",
        "chosen_policy": "Policy",
        "service_level": "Service %",
        "calculated_quantity": "Qty",
        "tokens_used": "Tokens",
        "status": "Status",
    }
    df_display = df_logs[list(display_cols.keys())].rename(columns=display_cols)
    df_display["Service %"] = df_display["Service %"].apply(lambda x: f"{x * 100:.0f}%")
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No agent activity yet. Run the agent check to generate logs.")

# ---------------------------------------------------------------------------
# Section 4: Pending Approvals
# ---------------------------------------------------------------------------
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
                    f"Service: {log['service_level'] * 100:.0f}%"
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
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Autonomous Inventory Agent Demo | Powered by Ollama (qwen2.5:7b) | "
    "This is an autonomous system, not a chatbot."
)
