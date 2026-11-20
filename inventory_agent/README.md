# 🍷 Autonomous Inventory Agent - Control Room Demo

A complete, runnable Python demo that proves an autonomous agent is **NOT** a chatbot.

## 🎯 What This Proves

This demo shows an **autonomous agent** that:
- ✅ Monitors inventory automatically (no user prompts needed)
- ✅ Detects anomalies using deterministic rules
- ✅ Uses a local LLM **only for diagnosis** (not calculations)
- ✅ Runs a deterministic optimizer for order quantities
- ✅ Applies tiered autonomy rules for approval decisions
- ✅ Logs all actions with full traceability

The LLM is a **component** (diagnosis only), not the entire system.

## 📁 File Structure

```
inventory_agent/
├── db.py              # Database initialization and helpers
├── agent.py           # LLM call + Pydantic schema + optimizer logic
├── app.py             # Streamlit UI (main entry point)
├── requirements.txt   # Python dependencies
├── test_agent.py      # Comprehensive test suite
└── inventory.db       # SQLite database (auto-created on first run)
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd inventory_agent/
pip install -r requirements.txt
```

### 2. Install Ollama (if not already installed)

Download from: https://ollama.com

### 3. Pull the LLM Model

```bash
ollama pull qwen2.5:7b
```

### 4. Run Tests (Optional but Recommended)

```bash
python test_agent.py
```

This validates all components work correctly, even without Ollama running.

### 5. Run the Streamlit App

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## 🎮 How to Use

### Main Interface

1. **View Current Inventory** - See all wines with stock levels
2. **Run Agent Check** - Click the big button to trigger autonomous scanning
3. **Review Results** - See diagnosis, policies, and order quantities
4. **Approve/Reject** - Handle pending approvals at the bottom

### Chaos Engine (Sidebar)

Inject disorder to test the agent:

- **🛒 Simulate Weekend Sales** - Reduces stock for 2 random wines
- **💀 Simulate Spoilage** - Removes 3 units from selected wine
- **⏳ Inject Supplier Delay** - Adds 3 days to lead time
- **🔄 Reset Database** - Restore to seed values

## 🏗️ Architecture

### Agent Pipeline

```
1. Watchdog (detect_anomalies)
   ↓
2. LLM Call (diagnosis only)
   ↓
3. Optimizer (deterministic calculation)
   ↓
4. Autonomy Decision (tiered rules)
   ↓
5. Log & Act
```

### Database Schema

**wines table:**
- sku (PK), name, current_stock, reorder_point
- unit_cost, lead_time_days, supplier_reliability

**agent_logs table:**
- id, timestamp, sku, trigger_reason
- llm_diagnosis, chosen_policy, service_level
- calculated_quantity, tokens_used, status

### Autonomy Rules

- **Auto-Approved:** total_cost ≤ $200 AND reliability ≥ 3
- **Pending Human:** total_cost > $200 OR reliability < 3

## 🧠 The LLM's Role

### What the LLM DOES:
- Analyze anomaly context and provide diagnosis
- Recommend a policy (min_max or order_up_to)
- Suggest a service level (0.90 - 0.99)
- Flag whether human approval may be needed

### What the LLM DOES NOT:
- Calculate order quantities (deterministic code does)
- Make final approval decisions (rules do)
- Access the database directly
- Run without the deterministic pipeline

## 📊 Seed Data

5 wines with realistic inventory data:

| SKU | Name | Stock | Reorder | Cost | Lead Time | Reliability |
|-----|------|-------|---------|------|-----------|-------------|
| SKU-001 | Chardonnay | 15 | 10 | $12 | 5 days | 4/5 |
| SKU-002 | Pinot Noir | 8 | 10 | $18 | 7 days | 3/5 |
| SKU-003 | Cabernet | 20 | 12 | $22 | 6 days | 5/5 |
| SKU-004 | Sauvignon Blanc | 5 | 8 | $10 | 4 days | 2/5 |
| SKU-005 | Prosecco | 12 | 10 | $14 | 5 days | 4/5 |

## 🔧 Troubleshooting

### "ollama package not installed"
```bash
pip install ollama
```

### "Ollama not responding"
```bash
# Start Ollama service
ollama serve

# In another terminal, verify model is pulled
ollama list
ollama pull qwen2.5:7b
```

### "No anomalies detected"
The agent only runs when anomalies exist. Use the Chaos Engine to inject events.

### Tests fail
```bash
# Run individual test functions
python -c "import test_agent; test_agent.test_database()"
```

## 📝 Key Design Decisions

1. **Deterministic Optimizer** - Order quantities are calculated, not hallucinated
2. **LLM for Diagnosis Only** - Context and policy, never math
3. **Tiered Autonomy** - Risk-based approval routing
4. **Full Traceability** - Every action logged with tokens used
5. **Local-First** - No cloud APIs, everything runs locally

## 🎓 Learning Outcomes

This demo teaches:
- How autonomous agents differ from chatbots
- The role of deterministic logic in AI systems
- Tiered autonomy and risk management
- Local LLM integration with Ollama
- Structured output parsing with Pydantic
- Full audit trails for AI decision-making

## 📄 License

MIT License - Use freely for learning and demonstration.

---

**Remember:** This is an autonomous system that **acts**, not a chatbot that **talks**.
