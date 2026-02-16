# ShadowGraph: A Semantic Knowledge Graph for AI-Driven Development

> **Store code intent in the graph where it lives, not in comments that disappear.**

ShadowGraph is a **persistent knowledge graph** for long-running AI agent development. It captures **why** code exists, **what constraints** it has, and **how it connects** to other parts of the system—enabling agents to understand context without reading thousands of lines of code or forgetting what you told them last session.

---

## 🤔 The Problem: Stateless Agents = Expensive Hallucinations

When building or maintaining a codebase over weeks with AI agents:

1. **Lost Context.** Each new conversation, agents start from scratch. You re-explain the same architecture decisions, business rules, and tradeoffs.
2. **Expensive Tokens.** You copy-paste code into prompts to restore context. A 100k codebase with an agent? That's thousands of wasted tokens per query.
3. **Hallucinations.** Without understanding *why* code exists, agents make assumptions and introduce bugs.
4. **Fragile Comments.** Even with inline documentation, comments rot, get deleted by refactors, and can't be queried.

**The Core Problem:** Code execution is a *graph* of dependencies and calls. But documentation is *linear*—written in comments alongside code, isolated from the structure they describe.

---

## 💡 The Solution: Intent as a Graph, Not as Comments

ShadowGraph mirrors the **structure of your code** with a **knowledge graph**:

- **Code = Nodes** (functions, classes, files)
- **Dependencies = Edges** (calls, imports, references)
- **Intent = Linked Thoughts** (business rules, constraints, design decisions)

Agents can now **intuitively navigate and query** this structure:

```
Agent: "Why does process_payment need to be idempotent?"

ShadowGraph:
  └─ Finds: function:payment.process_payment
  └─ Returns: Linked thought: "Stripe webhook can retry. Must be safe."
  └─ Also returns: Business rule: "Payments are always national DPD shipments from Berlin hub"
  └─ Total tokens: ~100 (vs. 5000 for reading 20 files)
```

**The Benefit:** Agents can recall *exactly what they need* without hallucinating or bloating the context window.

---

## ✨ How It Works

### 1. **Semantic Storage** — Not Line Numbers
- Thoughts are anchored to code via **AST hashes**, not line numbers
- Move a function → the thought moves with it
- Rename a class → the thought still finds it
- Change the logic → the thought is marked **STALE** and the agent is warned

### 2. **The 5 Essential Tools**

- **`remember(topic, context, file_path?, symbol_name?)`** — Save business rules, design decisions, constraints
- **`recall(query)`** — Query what you know about a symbol, business rule, or topic
- **`index(file_path)`** — Parse a file and register its symbols in the graph
- **`check(file_path?)`** — Detect stale thoughts when code changes
- **`create_file(path, content)`** — Write code to disk AND auto-register it in the graph
- **`debug_info()`** — Diagnostic info for troubleshooting

Simple, intentional verbs. No confusion.

### 3. **Team Knowledge** — Git-Tracked Thoughts
Thoughts are saved in `.shadow/graph.jsonl`:
- Commit them to Git alongside your code
- Teammates pull and **instantly inherit your context**
- No onboarding questions. The knowledge lives in the repo.

---

## 🚀 Getting Started

### Install
```bash
# Install from VS Code Marketplace
# (or build from source: npm run build)
```

### Quick Example

```python
# Agent saves business knowledge
remember("shipping", "All shipments are national DPD from our Berlin hub. Tracking: 123.22.123.1:7534/parcels")

# Agent indexes a new file they wrote
index("src/shipping/parcel_tracker.py")

# Agent recalls context before making changes
recall("shipping")
# Returns: Business rule about DPD + Berlin hub + tracking API

# Agent modifies code and re-indexes
# ... code changes ...
index("src/shipping/parcel_tracker.py")

# Agent checks for stale thoughts
check("src/shipping/parcel_tracker.py")
# Returns: "All anchors valid, no stale thoughts"
```

---

## 🎯 Why This Matters for Agent-Driven Development

**Traditional Workflow:**
- Agent reads 50 files → 10k tokens just for context
- Agent guesses at design intent → introduces bugs
- Next session, agent forgets everything → repeat

**ShadowGraph Workflow:**
- Agent queries graph for 1 symbol → 200 tokens of exact context
- Agent understands *why* code exists → makes intelligent changes
- Graph persists across sessions → agent remembers everything

**Cost: ~5% of the context tokens. Knowledge that doesn't disappear.**

---

## 🔬 Architecture

- **Extension:** VS Code (TypeScript) — displays codelens, decorations, commands
- **MCP Server:** Python (FastMCP) — parses code, manages graph, serves queries
- **Storage:** SQLite — local, portable, easy to version control
- **Parsing:** tree-sitter — multi-language AST support (Python, TypeScript, JS, Go, Rust, etc.)

---

## License

MIT. Use this in your projects, in teams, in AI workflows. The code is yours.

---

**Built for environments where agents maintain and evolve codebases over weeks or months.**
*Where context is everything, and tokens are expensive.*


