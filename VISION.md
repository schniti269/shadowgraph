# ShadowGraph Vision

> **North Star:** An agent should call ONE tool and get everything it needs to reason about a symbol. No file reading. No git commands. No reference browsing. One call. Done.

---

## The Problem We're Solving

Every agent tool that exists today does one thing:
- `read_file` → raw source (10k tokens of noise)
- `git_log` → commit history (unstructured text)
- `find_references` → file:line pairs (no context)
- `grep` → keyword matches (zero semantics)

So agents chain 6-8 tool calls to understand one function. That's the bug. **Tool sprawl is context bloat.**

ShadowGraph replaces all of them with a single parametrized query.

---

## The Model: Code Data Warehouse

A symbol is a **fact**. Every information source about that symbol is a **dimension**:

| Dimension | Source | Status |
|-----------|--------|--------|
| `knowledge` | Agent-written thoughts, decisions, todos | ✅ live |
| `git` | Commit history, blame, churn | 🔴 next |
| `syntax` | AST call graph, callers, callees | 🟡 after |
| `refs` | LSP go-to-definition, all-references | 🟡 after |
| `security` | Semgrep findings | ⚪ future |

OLAP operations on that fact table:
- **Drill-down** → `file → class → function`
- **Roll-up** → `function → module → workspace`
- **Cross-filter** → `symbols changed in git last 30d AND have stale thoughts`

---

## 5 Tools. That's It.

The entire surface area of what an agent needs to work with a codebase:

| Tool | Replaces |
|------|---------|
| `recall(symbol, dimensions?, depth?, filter?)` | read_file, git_log, find_references, grep, cat |
| `remember(topic, context, symbol?, parent_id?)` | comments, docs, any knowledge capture |
| `edit(file, symbol, thought, new_code)` | write_file (but forces WHY before WHAT) |
| `index(file_path)` | manual symbol registration |
| `check(file_path?)` | drift detection, coverage gaps |

`recall` is the workhorse. Everything else supports it.

---

## Storage: Right Tool for Each Job

**Two stores, one coherent interface:**

```
shadow.db          ← SQLite: nodes, edges, anchors
                     OLTP — fast single-row writes, FK integrity
                     Read by VS Code extension via sql.js (WASM)

shadow-facts.duckdb ← DuckDB: git_facts, syntax_facts, future dimensions
                      OLAP — columnar, aggregations, JSON/LIST types
                      Attached to shadow.db for cross-store joins
                      Never touched by the extension side
```

**Why hybrid and not one engine:**
- SQLite stays because the **extension reads it via sql.js** — that can't change without a full extension rewrite. It's the right store for graph writes (OLTP).
- DuckDB earns its place on the **analytical side** — one SQL expression with `GROUP BY`, `UNNEST`, JSON columns, and window functions replaces 40 lines of Python that iterate and aggregate dimension data. Less code, same result. That's the rule.

DuckDB attaches to the SQLite file directly:
```python
duckdb.execute("ATTACH 'shadow.db' AS graph (TYPE sqlite)")
# Now cross-store OLAP queries work — no ETL, no sync
```

---

## The Design Rule

> **Less code achieving the same thing = good.**

Every architectural decision gets judged by this. DuckDB wins on the analytical side because it turns 40-line Python loops into 4-line SQL. The dimension provider pattern is worth adding because it isolates each data source behind one interface — adding `security` later touches zero existing code.

**What this means for `recall()`:**
- The Python implementation fans out to dimension providers
- Each provider is 30-50 lines max
- The merged response is terse structured JSON — not prose, not raw source
- An agent reading the response needs zero post-processing

---

## Roadmap

| Phase | Goal | What ships |
|-------|------|-----------|
| ✅ v1.0 | Consolidated 5-tool set, graph store working | `knowledge` dimension only |
| 🔴 v1.1 | Git dimension | `recall(dimensions=["git"])` returns churn, authors, recent commits |
| 🟡 v1.2 | OLAP params + tree notes | `depth`, `filter`, `parent_id` on remember |
| 🟡 v1.3 | Syntax dimension | call graph via tree-sitter, callers/callees in recall |
| 🟡 v2.0 | LSP dimension | refs from Pylance/tsserver via VS Code extension proxy |
| ⚪ v3.0 | Security dimension | semgrep findings per symbol |

---

## Architecture Diagram

```
Agent
  │
  └─ recall("function:charge", dimensions=["knowledge","git"], depth=2)
       │
       ▼
  MCP Server (Python)
  ├── knowledge provider  → queries shadow.db (SQLite via python sqlite3)
  ├── git provider        → queries shadow-facts.duckdb + git subprocess
  ├── syntax provider     → queries shadow-facts.duckdb (tree-sitter precomputed)
  └── [future providers]
       │
       ▼
  Merged JSON response
  {symbol, location, dimensions: {knowledge: {...}, git: {...}}}

VS Code Extension (TypeScript)
  └── Reads shadow.db directly via sql.js (WASM)
      CodeLens, decorations, drift warnings — no Python round-trip
```

---

*Last updated: 2026-02-19 | v1.0.0 | 60/60 tests passing*
