# ShadowGraph 🧠
### The Missing Semantic Layer for AI Coding Agents.

![ShadowGraph Logo](icons/shadowgraph-logo.png)

[![VS Code](https://img.shields.io/badge/VS%20Code-Extension-blue)](https://marketplace.visualstudio.com)
[![MCP Ready](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **"Don't just commit code. Commit understanding."**

**ShadowGraph** creates a persistent, invisible "Shadow Layer" alongside your code. It captures **Intent**, **Constraints**, and **Relationships** in a graph database that AI agents can query—eliminating hallucinations and context window bloat.

---

## 💥 The Problem: "Amnesic" Agents

When you ask an AI to refactor code, it has to read thousands of lines of text to guess *why* the code exists.
* **It guesses.** (Hallucination)
* **It misses context.** (Bug Introduction)
* **It costs money.** (Massive Token Usage)

**Comments don't help.** They rot, they lie, and they can't be queried.

## 🛠️ The Solution: A Semantic Knowledge Graph

ShadowGraph runs locally. It parses your code into an AST and attaches "Thought Nodes" to functions, classes, and blocks.

### Compare the Difference

| **Traditional AI Workflow** ❌ | **ShadowGraph Workflow** ✅ |
| :--- | :--- |
| **Input:** 50 Files (10k Tokens) | **Input:** 1 Graph Query (200 Tokens) |
| **Context:** "Here is a wall of text." | **Context:** "Here is the exact dependency chain." |
| **Reasoning:** Probabilistic Guessing | **Reasoning:** Causal Logic |
| **Maintenance:** Comments drift & break | **Maintenance:** Links track code via AST Hash |

---

## ✨ Key Features

### 1. ⚓ Semantic Anchoring (Refactor-Proof Notes)
We don't link to line numbers. We link to **AST Hashes**.
* Move a function? **The note follows.**
* Rename a file? **The note follows.**
* Change the logic? **The note is marked `STALE` and the Agent is warned.**

### 2. 📉 Massive Context Reduction
Instead of reading the whole file, your Agent queries the graph:
```python
# Agent Query:
query_blast_radius("ProcessPayment", depth=2)

# Result (JSON):
{
  "node": "ProcessPayment",
  "constraint": "MUST be idempotent (Stripe Req)",
  "dependency": "UserDB (Status: STALE - Changed 1hr ago)",
  "risk": "High - Affects Checkout Flow"
}

```

### 3. 🧠 The "Hive Mind" (Git Integration)

Your thoughts are saved in `.shadow/graph.jsonl`.

* Commit them to Git.
* Teammates pull the repo and **instantly inherit your context**.
* Zero onboarding time.

### 4. 🛡️ Semantic CI

Run `shadow-check` in your CI pipeline. If you modify code that has a `CRITICAL` constraint attached without updating the graph, the build fails.

> *"You changed the Auth Logic but ignored the 'Security Audit' constraint. Please update the graph."*

---

## 🚀 Getting Started

### Installation

1. Install the **ShadowGraph** extension from the VS Code Marketplace.
2. The internal MCP Server will start automatically.

### Usage with AI Agents (Cursor, Windsurf, Copilot)

**1. Index your workspace:**

> "ShadowGraph: Index this codebase."

**2. Add a Thought:**
Highlight code and ask your Agent:

> "Attach a thought to this block: 'We use a spinlock here because the thread scheduler is unreliable on Windows.'"

**3. Debug with Superpowers:**

> "Why is the `Login` function failing? Check the ShadowGraph for recent dependency changes."

---

## 🔬 The Architecture

* **Frontend:** VS Code Extension (TypeScript)
* **Backend:** Local Python MCP Server
* **Storage:** SQLite (Graph) + sqlite-vec (Vector Search)
* **Parsing:** Tree-sitter (Multi-language support)

## 🤝 Contributing

ShadowGraph is open-source. We are building the standard protocol for Code-Intent Mapping.
[Link to Contributing Guide]

---

*Built for the Age of Agents.*


