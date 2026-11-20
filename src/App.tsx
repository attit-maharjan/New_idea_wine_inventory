import { useState } from "react";

const dbCode = `"""
Database initialization and helpers for the Autonomous Inventory Agent.
Uses SQLite with file: inventory.db
"""

import sqlite3
import os
from typing import List, Dict, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

SEED_DATA = [
    ("SKU-001", "Chardonnay", 15, 10, 12.0, 5, 4),
    ("SKU-002", "Pinot Noir", 8, 10, 18.0, 7, 3),
    ("SKU-003", "Cabernet", 20, 12, 22.0, 6, 5),
    ("SKU-004", "Sauvignon Blanc", 5, 8, 10.0, 4, 2),
    ("SKU-005", "Prosecco", 12, 10, 14.0, 5, 4),
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema and seed data."""
    conn = get_connection()
    cursor = conn.cursor()
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
    cursor.execute("SELECT COUNT(*) FROM wines")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO wines (sku, name, current_stock, reorder_point, "
            "unit_cost, lead_time_days, supplier_reliability) VALUES (?, ?, ?, ?, ?, ?, ?)",
            SEED_DATA,
        )
    conn.commit()
    conn.close()

# ... (additional helper functions for CRUD operations)`;

const agentCode = `"""
Autonomous Inventory Agent - Core logic.
Contains: anomaly detection, LLM integration, deterministic optimizer, autonomy rules.
"""

from math import ceil
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import db


class LLMResponse(BaseModel):
    """Structured response from the LLM."""
    diagnosis: str = Field(description="One-sentence diagnosis of the anomaly")
    chosen_policy: str = Field(description="Either 'min_max' or 'order_up_to'")
    service_level: float = Field(ge=0.90, le=0.99)
    requires_human_approval: bool = Field(description="Whether human approval is needed")


def detect_anomalies() -> List[Dict]:
    """Returns list of wine dicts where:
    current_stock <= reorder_point OR supplier_reliability <= 2"""
    wines = db.get_all_wines()
    anomalies = []
    for wine in wines:
        if (wine["current_stock"] <= wine["reorder_point"] or
                wine["supplier_reliability"] <= 2):
            reasons = []
            if wine["current_stock"] <= wine["reorder_point"]:
                reasons.append("low_stock")
            if wine["supplier_reliability"] <= 2:
                reasons.append("unreliable_supplier")
            wine["trigger_reason"] = " + ".join(reasons)
            anomalies.append(wine)
    return anomalies


def call_llm(wine: Dict) -> Optional[LLMResponse]:
    """Call the local Ollama LLM (qwen2.5:7b) for diagnosis."""
    import ollama
    # ... LLM call with system prompt and user prompt
    # Parse response with Pydantic, count tokens


def calculate_order_quantity(wine: Dict, policy: str, service_level: float) -> int:
    """Deterministic order quantity calculation."""
    if policy == "min_max":
        return wine["reorder_point"] * 2 - wine["current_stock"]
    elif policy == "order_up_to":
        avg_daily_demand = wine["reorder_point"] / 30.0
        safety_stock = avg_daily_demand * wine["lead_time_days"] * (1.0 - service_level) * 2
        target = avg_daily_demand * (wine["lead_time_days"] + 7) + safety_stock
        return max(0, ceil(target - wine["current_stock"]))
    return 0


def decide_autonomy(order_qty: int, unit_cost: float, reliability: int) -> str:
    """Tiered autonomy: auto_approve if cost<=200 AND reliability>=3."""
    total_cost = order_qty * unit_cost
    if total_cost <= 200 and reliability >= 3:
        return "auto_approved"
    return "pending_human"


def process_anomaly(wine: Dict) -> Dict:
    """Full pipeline: LLM → Optimizer → Autonomy → Log."""
    llm_result = call_llm(wine)
    order_qty = calculate_order_quantity(wine, llm_result.chosen_policy, llm_result.service_level)
    status = decide_autonomy(order_qty, wine["unit_cost"], wine["supplier_reliability"])
    # ... log to database and return result`;

const appCode = `"""
Autonomous Inventory Agent Control Room - Streamlit UI
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import db
import agent

st.set_page_config(page_title="🍷 Autonomous Inventory Agent", layout="wide")

db.init_db()

# Sidebar - Chaos Engine
with st.sidebar:
    st.header("⚡ Chaos Engine")
    
    if st.button("🛒 Simulate Weekend Sales"):
        # Subtracts random 3-8 from 2 random wines
        ...
    
    if st.button("💀 Simulate Spoilage"):
        # Subtracts 3 from selected wine
        ...
    
    if st.button("⏳ Inject Supplier Delay"):
        # Adds +3 days to lead_time
        ...
    
    if st.button("🔄 Reset Database"):
        db.reset_db()
        st.rerun()
    
    st.metric("🪙 Total Tokens Used Today", f"{db.get_total_tokens():,}")

# Main Area
st.title("🍷 Autonomous Inventory Agent Control Room")

# Current Inventory
st.dataframe(pd.DataFrame(db.get_all_wines()))

# Run Agent
if st.button("🔄 Run Autonomous Agent Check", type="primary"):
    anomalies = agent.detect_anomalies()
    if not anomalies:
        st.success("✅ System stable. Agent slept. 0 tokens used.")
    else:
        for wine in anomalies:
            result = agent.process_anomaly(wine)
            # Display result cards with expanders

# Activity Log
st.dataframe(pd.DataFrame(db.get_recent_logs(20)))

# Pending Approvals
for log in db.get_pending_approvals():
    col1, col2, col3 = st.columns([3, 1, 1])
    # Show approve/reject buttons`;

type TabId = "overview" | "architecture" | "files" | "setup";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [activeFile, setActiveFile] = useState<string>("db.py");

  const fileContents: Record<string, string> = {
    "db.py": dbCode,
    "agent.py": agentCode,
    "app.py": appCode,
  };

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: "overview", label: "Overview", icon: "📋" },
    { id: "architecture", label: "Architecture", icon: "🏗️" },
    { id: "files", label: "Source Code", icon: "📁" },
    { id: "setup", label: "Setup & Run", icon: "🚀" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-purple-500/30 bg-black/30 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center gap-4">
            <span className="text-5xl">🍷</span>
            <div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-300 to-pink-300 bg-clip-text text-transparent">
                Autonomous Inventory Agent
              </h1>
              <p className="text-gray-400 mt-1">
                A complete demo proving an autonomous agent is{" "}
                <span className="text-red-400 font-semibold">NOT</span> a chatbot
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="border-b border-purple-500/20 bg-black/20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-5 py-3 text-sm font-medium transition-all rounded-t-lg ${
                  activeTab === tab.id
                    ? "bg-purple-600/30 text-purple-200 border-b-2 border-purple-400"
                    : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
                }`}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === "overview" && <OverviewSection />}
        {activeTab === "architecture" && <ArchitectureSection />}
        {activeTab === "files" && (
          <FilesSection
            activeFile={activeFile}
            setActiveFile={setActiveFile}
            fileContents={fileContents}
          />
        )}
        {activeTab === "setup" && <SetupSection />}
      </main>

      {/* Footer */}
      <footer className="border-t border-purple-500/20 bg-black/30 mt-12">
        <div className="max-w-7xl mx-auto px-6 py-6 text-center text-gray-500 text-sm">
          <p>
            Built with Python • Streamlit • Ollama (qwen2.5:7b) • Pydantic • SQLite
          </p>
          <p className="mt-1">
            This is an autonomous system that acts, not a chatbot that talks.
          </p>
        </div>
      </footer>
    </div>
  );
}

function OverviewSection() {
  return (
    <div className="space-y-8">
      {/* Hero Card */}
      <div className="bg-gradient-to-r from-purple-800/40 to-pink-800/40 rounded-2xl p-8 border border-purple-500/30">
        <h2 className="text-2xl font-bold mb-4">🎯 What This Proves</h2>
        <p className="text-gray-300 text-lg leading-relaxed">
          This demo shows an <strong className="text-purple-300">autonomous agent</strong> that
          monitors inventory, detects anomalies using deterministic rules, calls a local LLM
          for <em>diagnosis only</em>, runs a <em>deterministic optimizer</em> for order
          quantities, and applies <em>tiered autonomy</em> to decide what needs human approval.
        </p>
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-black/30 rounded-xl p-4 border border-green-500/30">
            <div className="text-green-400 font-bold text-lg">✅ Agent Does</div>
            <ul className="mt-2 text-sm text-gray-300 space-y-1">
              <li>• Scans inventory automatically</li>
              <li>• Detects anomalies via rules</li>
              <li>• Uses LLM for diagnosis</li>
              <li>• Calculates orders deterministically</li>
              <li>• Auto-approves or queues</li>
            </ul>
          </div>
          <div className="bg-black/30 rounded-xl p-4 border border-red-500/30">
            <div className="text-red-400 font-bold text-lg">❌ Agent Doesn't</div>
            <ul className="mt-2 text-sm text-gray-300 space-y-1">
              <li>• Wait for user messages</li>
              <li>• Calculate quantities via LLM</li>
              <li>• Make unbounded decisions</li>
              <li>• Require conversation</li>
              <li>• Hallucinate order numbers</li>
            </ul>
          </div>
          <div className="bg-black/30 rounded-xl p-4 border border-blue-500/30">
            <div className="text-blue-400 font-bold text-lg">🔑 Key Insight</div>
            <p className="mt-2 text-sm text-gray-300">
              The LLM is a <em>component</em> (diagnosis only), not the entire system.
              Deterministic logic handles math. Autonomy tiers handle risk.
            </p>
          </div>
        </div>
      </div>

      {/* Feature Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <FeatureCard
          icon="👁️"
          title="Deterministic Watchdog"
          description="Rules-based anomaly detection. No LLM needed to know when stock is low."
        />
        <FeatureCard
          icon="🧠"
          title="LLM for Diagnosis Only"
          description="Local Ollama (qwen2.5:7b) provides context and policy recommendation. Never calculates quantities."
        />
        <FeatureCard
          icon="🧮"
          title="Deterministic Optimizer"
          description="Min-max or order-up-to policies with safety stock calculations. Always reproducible."
        />
        <FeatureCard
          icon="🎛️"
          title="Tiered Autonomy"
          description="Auto-approve low-risk orders. Queue high-cost or unreliable-supplier orders for humans."
        />
        <FeatureCard
          icon="⚡"
          title="Chaos Engine"
          description="Inject sales, spoilage, and delays via the sidebar. Watch the agent respond autonomously."
        />
        <FeatureCard
          icon="🔒"
          title="Fully Local"
          description="No cloud APIs. Ollama runs locally. SQLite database. Everything stays on your machine."
        />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div className="bg-white/5 rounded-xl p-6 border border-white/10 hover:border-purple-500/30 transition-all">
      <div className="text-3xl mb-3">{icon}</div>
      <h3 className="text-lg font-semibold text-purple-200">{title}</h3>
      <p className="text-gray-400 mt-2 text-sm">{description}</p>
    </div>
  );
}

function ArchitectureSection() {
  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold">🏗️ System Architecture</h2>

      {/* Flow Diagram */}
      <div className="bg-black/40 rounded-2xl p-8 border border-purple-500/20">
        <h3 className="text-xl font-semibold mb-6 text-center text-purple-300">Agent Pipeline</h3>
        <div className="flex flex-col md:flex-row items-center justify-center gap-4">
          <FlowStep number={1} title="Watchdog" desc="detect_anomalies()" color="blue" />
          <FlowArrow />
          <FlowStep number={2} title="LLM Call" desc="call_llm()" color="purple" />
          <FlowArrow />
          <FlowStep number={3} title="Optimizer" desc="calculate_order_qty()" color="green" />
          <FlowArrow />
          <FlowStep number={4} title="Autonomy" desc="decide_autonomy()" color="orange" />
          <FlowArrow />
          <FlowStep number={5} title="Log & Act" desc="insert_log()" color="pink" />
        </div>
      </div>

      {/* Data Flow */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <h3 className="text-lg font-semibold text-blue-300 mb-4">📊 Database Schema</h3>
          <div className="space-y-4">
            <div>
              <code className="text-sm bg-black/40 px-2 py-1 rounded text-green-300">wines</code>
              <ul className="mt-2 text-sm text-gray-400 space-y-1 ml-4">
                <li>sku (PK), name, current_stock, reorder_point</li>
                <li>unit_cost, lead_time_days, supplier_reliability</li>
              </ul>
            </div>
            <div>
              <code className="text-sm bg-black/40 px-2 py-1 rounded text-green-300">agent_logs</code>
              <ul className="mt-2 text-sm text-gray-400 space-y-1 ml-4">
                <li>id, timestamp, sku, trigger_reason</li>
                <li>llm_diagnosis, chosen_policy, service_level</li>
                <li>calculated_quantity, tokens_used, status</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <h3 className="text-lg font-semibold text-orange-300 mb-4">🎛️ Autonomy Rules</h3>
          <div className="space-y-3">
            <div className="bg-green-900/30 rounded-lg p-3 border border-green-500/30">
              <div className="font-semibold text-green-300">✅ Auto-Approved</div>
              <div className="text-sm text-gray-400">total_cost ≤ $200 AND reliability ≥ 3</div>
            </div>
            <div className="bg-yellow-900/30 rounded-lg p-3 border border-yellow-500/30">
              <div className="font-semibold text-yellow-300">⏳ Pending Human</div>
              <div className="text-sm text-gray-400">total_cost &gt; $200 OR reliability &lt; 3</div>
            </div>
          </div>
        </div>
      </div>

      {/* LLM Role */}
      <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-2xl p-8 border border-purple-500/20">
        <h3 className="text-xl font-semibold mb-4">🧠 The LLM's Role (and Limits)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-green-300 font-semibold mb-2">LLM DOES:</h4>
            <ul className="text-sm text-gray-300 space-y-2">
              <li className="flex items-start gap-2">
                <span className="text-green-400">•</span>
                Analyze anomaly context and provide a diagnosis
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">•</span>
                Recommend a policy (min_max or order_up_to)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">•</span>
                Suggest a service level (0.90 - 0.99)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">•</span>
                Flag whether human approval may be needed
              </li>
            </ul>
          </div>
          <div>
            <h4 className="text-red-300 font-semibold mb-2">LLM DOES NOT:</h4>
            <ul className="text-sm text-gray-300 space-y-2">
              <li className="flex items-start gap-2">
                <span className="text-red-400">•</span>
                Calculate order quantities (deterministic code does)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400">•</span>
                Make final approval decisions (rules do)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400">•</span>
                Access the database directly
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400">•</span>
                Run without the deterministic pipeline
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function FlowStep({ number, title, desc, color }: { number: number; title: string; desc: string; color: string }) {
  const colors: Record<string, string> = {
    blue: "border-blue-500/50 bg-blue-900/30",
    purple: "border-purple-500/50 bg-purple-900/30",
    green: "border-green-500/50 bg-green-900/30",
    orange: "border-orange-500/50 bg-orange-900/30",
    pink: "border-pink-500/50 bg-pink-900/30",
  };
  return (
    <div className={`rounded-xl p-4 border ${colors[color]} text-center min-w-[140px]`}>
      <div className="text-xs text-gray-400 mb-1">Step {number}</div>
      <div className="font-semibold text-white">{title}</div>
      <code className="text-xs text-gray-400 mt-1 block">{desc}</code>
    </div>
  );
}

function FlowArrow() {
  return <div className="text-purple-400 text-2xl hidden md:block">→</div>;
}

function FilesSection({
  activeFile,
  setActiveFile,
  fileContents,
}: {
  activeFile: string;
  setActiveFile: (f: string) => void;
  fileContents: Record<string, string>;
}) {
  const files = ["db.py", "agent.py", "app.py", "requirements.txt"];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">📁 Source Code</h2>
      <p className="text-gray-400">
        All files are in the <code className="bg-black/40 px-2 py-0.5 rounded text-purple-300">inventory_agent/</code> directory.
      </p>

      <div className="flex flex-col md:flex-row gap-6">
        {/* File List */}
        <div className="md:w-56 shrink-0">
          <div className="bg-black/40 rounded-xl border border-white/10 overflow-hidden">
            {files.map((file) => (
              <button
                key={file}
                onClick={() => setActiveFile(file)}
                className={`w-full text-left px-4 py-3 text-sm border-b border-white/5 transition-all ${
                  activeFile === file
                    ? "bg-purple-600/30 text-purple-200"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                <span className="mr-2">{file.endsWith(".py") ? "🐍" : "📄"}</span>
                {file}
              </button>
            ))}
          </div>
        </div>

        {/* Code Display */}
        <div className="flex-1 min-w-0">
          <div className="bg-black/60 rounded-xl border border-white/10 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-black/40 border-b border-white/10">
              <span className="text-sm text-gray-400">
                inventory_agent/{activeFile}
              </span>
              <span className="text-xs text-gray-500">Python</span>
            </div>
            <pre className="p-4 overflow-x-auto text-sm text-gray-300 max-h-[600px] overflow-y-auto">
              <code>{activeFile === "requirements.txt" ? "streamlit\nollama\npydantic" : fileContents[activeFile]}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function SetupSection() {
  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold">🚀 Setup & Run</h2>

      {/* Prerequisites */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-purple-300 mb-4">Prerequisites</h3>
        <ul className="space-y-3 text-gray-300">
          <li className="flex items-start gap-3">
            <span className="text-green-400 text-lg">✓</span>
            <div>
              <strong>Python 3.9+</strong> installed
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-green-400 text-lg">✓</span>
            <div>
              <strong>Ollama</strong> installed and running{" "}
              <a href="https://ollama.com" className="text-purple-400 underline" target="_blank" rel="noreferrer">
                (ollama.com)
              </a>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-green-400 text-lg">✓</span>
            <div>
              <strong>qwen2.5:7b</strong> model pulled:{" "}
              <code className="bg-black/40 px-2 py-0.5 rounded text-sm">ollama pull qwen2.5:7b</code>
            </div>
          </li>
        </ul>
      </div>

      {/* Installation Steps */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-purple-300 mb-4">Installation</h3>
        <div className="space-y-4">
          <Step number={1} title="Navigate to the project folder">
            <code className="block bg-black/60 rounded-lg p-3 text-green-300">
              cd inventory_agent/
            </code>
          </Step>
          <Step number={2} title="Install Python dependencies">
            <code className="block bg-black/60 rounded-lg p-3 text-green-300">
              pip install -r requirements.txt
            </code>
          </Step>
          <Step number={3} title="Pull the LLM model (if not already done)">
            <code className="block bg-black/60 rounded-lg p-3 text-green-300">
              ollama pull qwen2.5:7b
            </code>
          </Step>
          <Step number={4} title="Run the test suite (validates all components)">
            <code className="block bg-black/60 rounded-lg p-3 text-green-300">
              python test_agent.py
            </code>
          </Step>
          <Step number={5} title="Run the Streamlit app">
            <code className="block bg-black/60 rounded-lg p-3 text-green-300">
              streamlit run app.py
            </code>
          </Step>
        </div>
      </div>

      {/* Usage Guide */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-purple-300 mb-4">How to Use</h3>
        <div className="space-y-4 text-gray-300">
          <div className="flex items-start gap-3">
            <span className="bg-purple-600/40 rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold shrink-0">1</span>
            <p>The app opens in your browser. You'll see the current inventory table.</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-purple-600/40 rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold shrink-0">2</span>
            <p>Use the <strong>Chaos Engine</strong> sidebar to inject events (sales, spoilage, delays).</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-purple-600/40 rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold shrink-0">3</span>
            <p>Click <strong>"Run Autonomous Agent Check"</strong> — the agent scans, diagnoses, and acts.</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="bg-purple-600/40 rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold shrink-0">4</span>
            <p>Review results in expanders. Approve or reject pending orders at the bottom.</p>
          </div>
        </div>
      </div>

      {/* File Structure */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-purple-300 mb-4">File Structure</h3>
        <pre className="bg-black/60 rounded-lg p-4 text-sm text-gray-300">
{`inventory_agent/
├── db.py              # Database init, schema, CRUD helpers
├── agent.py           # Anomaly detection, LLM call, optimizer, autonomy
├── app.py             # Streamlit UI (main entry point)
├── test_agent.py      # Comprehensive test suite
├── requirements.txt   # Python dependencies
└── inventory.db       # SQLite database (auto-created on first run)`}
        </pre>
      </div>
    </div>
  );
}

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="bg-purple-600/40 rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold">
          {number}
        </span>
        <span className="font-medium text-gray-200">{title}</span>
      </div>
      {children}
    </div>
  );
}
