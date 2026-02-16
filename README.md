# ShadowGraph

> **Semantic Intent Preservation for Code.** Don't just commit code. Commit understanding.

ShadowGraph is a VS Code extension that creates a "semantic shadow layer" for your codebase—a living graph database that links developer thoughts, architectural decisions, and constraints directly to code symbols via stable AST anchors. When your code changes, ShadowGraph detects drift and surfaces context to AI agents, preventing hallucinations and accelerating debugging.

## The Problem

Modern codebases suffer from "tribal knowledge" loss:
- Comments drift out of sync with code (fragile line number anchors)
- Architectural decisions are lost in Slack threads or outdated wikis
- Onboarding takes months because intent is invisible in the text
- Debugging requires reading the whole codebase instead of the relevant subgraph
- CI/CD validates syntax and tests, but misses **intent violations** ("This payment code MUST be idempotent")

## The Solution

ShadowGraph preserves developer intent in a queryable graph:

1. **Anchor thoughts to symbols** (not lines): "Why do we swallow Stripe errors here?"
2. **Serialize the graph to git**: Team members pull code and instantly see context
3. **Query dependencies surgically**: "What could break if I change this?" (95% less context noise)
4. **Validate constraints in CI**: "Payment code must be idempotent" — enforced in the pipeline

## Key Features

### 🧠 Semantic CodeLens
- Hover over a function/class to see all attached thoughts
- Timestamps show when context was added
- Stale anchor warnings: "This code changed since the last thought was added"

### 🌐 Team Collaboration (Hive Mind)
- Serialize your local graph to `.shadow/graph.jsonl` and commit to git
- Team pulls code = instantly sees thoughts + dependency maps
- Solves "Bus Factor 1" — knowledge isn't tribal anymore

### 🎯 Blast Radius Analysis
- Query the graph to understand impact: `query_blast_radius("PaymentProcessor", depth=2)`
- Returns: dependencies, dependents, attached thoughts, stale flags
- AI agents use this to debug with precision (not hallucination)

### 🛡️ Semantic CI/CD
- Define constraints: "Payments must be idempotent", "No Math.random() in security code"
- `graph-check` CLI validates code changes against constraints
- Prevents silent failures where tests pass but intent is violated

### 🔄 Multi-Language Support
- Python, TypeScript, JavaScript, TSX
- Tree-sitter AST parsing with stable SHA256 hashes (whitespace-insensitive)
- Automatic symbol extraction (functions, classes)

## Installation

### From VS Code Marketplace
1. Open VS Code Extensions (Cmd+Shift+X / Ctrl+Shift+X)
2. Search for "ShadowGraph"
3. Click Install
4. Reload VS Code

### From Source (Development)
```bash
git clone https://github.com/yourusername/shadowgraph.git
cd shadowgraph
npm install
npm run build
# Open in Extension Development Host: F5
```

## Quick Start

### 1. Initialize Your First Thought

Open a Python/TypeScript file and run:
```
Command Palette → ShadowGraph: Index Current File
```

This extracts all functions and classes into the graph database.

### 2. Add Context to a Symbol

Click on a function, then:
```
Command Palette → ShadowGraph: Add Thought
```

Example thought:
> "⚠️ This regex is brittle because Safari doesn't support lookbehinds. We tried using a Babel plugin but it bloated the bundle by 12KB."

The thought is now **anchored to the function's AST**, not a line number. If someone refactors the function, the thought stays attached.

### 3. Share with Your Team

```bash
git add .shadow/graph.jsonl
git commit -m "docs: add architectural notes via ShadowGraph"
git push
```

Team members pull the repo. Their local ShadowGraph automatically hydrates from `graph.jsonl`.

### 4. Query Dependencies (Debugging)

Use the AI agent workflow:
```
Copilot Chat → Configure Tools → Enable "ShadowGraph"
Agent: "Why does PaymentProcessor throw 500 errors?"
Agent calls: query_blast_radius("PaymentProcessor", depth=2)
Returns: Dependencies, thoughts, stale flags
Agent diagnoses: "CurrencyConverter changed return type to string 2 hours ago"
```

### 5. Enforce Constraints

Define a constraint in your project:
```
ShadowGraph: Add Constraint
"Payments must be idempotent"
```

In CI, run:
```bash
graph-check .vscode/shadow.db src/ --fail-on critical
```

Pipeline fails if payment code is modified without updating the constraint acknowledgment.

## Core Concepts

### Nodes (3 Types)
- **CODE_BLOCK**: Function, class, or module extracted by tree-sitter
- **THOUGHT**: Developer notes, architecture decisions, trade-off explanations
- **CONSTRAINT**: Rules ("No Math.random() in crypto"), requirements ("Session mgmt must link to AuthService")

### Edges (5 Types)
- **HAS_THOUGHT**: CODE_BLOCK → THOUGHT (thought is attached to code)
- **DEPENDS_ON**: CODE_BLOCK → CODE_BLOCK (function calls, imports)
- **REQUIRED_BY**: CODE_BLOCK → CONSTRAINT (code must satisfy this rule)
- **STALE_DUE_TO**: ANCHOR → ANCHOR (dependency changed, making this code possibly outdated)
- **IMPACTS**: For blast radius queries (inverse of DEPENDS_ON)

### Database Location
- **Local**: `.vscode/shadow.db` (SQLite + WAL mode)
  - Not committed to git (like `node_modules/`)
  - Regenerated from `graph.jsonl` on pull
  - Live reads/writes by extension

- **Shared**: `.shadow/graph.jsonl` (JSONL, one node/edge per line)
  - Committed to git, versioned, mergeable
  - Serialized snapshot of the graph
  - Team collaboration backbone

## MCP Tools (For AI Agents)

All tools are exposed to Copilot Chat via the Model Context Protocol (MCP):

### `index_file(file_path)`
Parse and extract all symbols from a file.
```json
{
  "symbols": ["function:login", "class:AuthService"],
  "hashes": {"function:login": "abc123..."}
}
```

### `add_thought(file_path, symbol_name, thought_text)`
Attach a note to a symbol.
```json
{
  "thought_id": "thought:xyz789",
  "linked_to": "code:auth.ts:function:login",
  "created_at": "2026-02-15T10:30:00Z"
}
```

### `get_context(file_path, symbol_name)`
Retrieve code + all linked thoughts (perfect for agent prompting).
```json
{
  "symbol": "function:login",
  "code": "async function login(user) { ... }",
  "thoughts": [
    {"id": "thought:1", "text": "⚠️ Stripe error swallowing...", "created_at": "2026-02-15..."},
    {"id": "thought:2", "text": "TODO: Add 2FA support", "created_at": "2026-02-14..."}
  ]
}
```

### `edit_code_with_thought(file_path, symbol_name, thought_text, new_code?)`
Force agents to document WHY before editing code.
```json
{
  "status": "ok",
  "thought_id": "thought:abc",
  "message": "Thought recorded. You may now edit the code."
}
```

### `check_drift(file_path)`
Detect code changes since last indexing.
```json
{
  "stale_symbols": [
    {"symbol": "function:login", "reason": "Code changed 2 hours ago"}
  ]
}
```

### `query_blast_radius(symbol_name, depth=2)` ⭐ NEW
Recursively retrieve dependencies, dependents, and attached context.
```json
{
  "origin": {"symbol": "PaymentProcessor", "thoughts": ["⚠️ Swallow Stripe errors..."]},
  "dependencies": [
    {"symbol": "CurrencyConverter", "stale": true, "changed": "2h ago"}
  ],
  "dependents": [
    {"symbol": "OrderService", "impacts": ["charge() calls"]}
  ]
}
```

### `add_constraint(symbol_name, rule_text, severity)` ⭐ NEW
Define a rule that code must follow.
```json
{
  "constraint_id": "constraint:idempotent_payments",
  "applies_to": "PaymentProcessor",
  "severity": "critical"
}
```

### `validate_constraints(file_path)` ⭐ NEW
Check if modified code violates constraints.
```json
{
  "violations": [
    {"constraint": "idempotent_payments", "status": "VIOLATED", "severity": "critical"}
  ]
}
```

## Configuration

Open VS Code Settings → "ShadowGraph":

- **`shadowgraph.pythonPath`**: Path to Python 3.10+ (auto-detect if not set)
- **`shadowgraph.enableCodeLens`**: Show thought counts in editor (default: true)
- **`shadowgraph.enableStaleDecorations`**: Show stale anchor warnings (default: true)
- **`shadowgraph.autoIndex`**: Index files on save (default: false)
- **`shadowgraph.enableGitIntegration`**: Auto-load `.shadow/graph.jsonl` on pull (default: true)

## Architecture

```
┌─ VS Code Extension (TypeScript) ──────────────────┐
│  - CodeLens (show thought counts)                  │
│  - Decorations (stale warnings)                    │
│  - File watcher (reload on DB change)              │
│  - Git integration (load graph.jsonl)              │
└────────────────┬─────────────────────────────────┘
                 │ MCP (stdio)
                 ↓
┌─ Python MCP Server (FastMCP) ─────────────────────┐
│  - 8 tools: index_file, add_thought, ... → Copilot│
│  - Tree-sitter AST parsing                         │
│  - Drift detection (hash comparison)               │
│  - Constraint validation                           │
└────────────────┬─────────────────────────────────┘
                 │ SQLite
                 ↓
        .vscode/shadow.db (local)
        .shadow/graph.jsonl (shared)
```

**Key Design Decisions:**
- **sql.js for reads** (TypeScript): Pure WASM, no native compilation headaches
- **sqlite3 for writes** (Python): Full SQL, transactions, WAL mode
- **AST-hash anchoring**: Symbols are anchored by whitespace-stripped SHA256 hashes, immune to formatting changes
- **Prefixed symbol names**: Database stores `"function:login"`, `"class:AuthService"` for clear type information
- **Timestamps on all nodes**: Enables temporal queries ("Show me what changed in the last hour")

## Use Cases

### 1. **Onboarding**
New dev asks: "Why do we use TypeORM here?"
Agent queries graph → finds linked constraint "Legacy monolith ORMs" → explains.

### 2. **Debugging at 3 AM**
Error in `PaymentProcessor.charge()`:
Agent calls `query_blast_radius("PaymentProcessor")` → sees attached thought:
> "⚠️ Stripe error swallowing due to idempotency keys"
Instantly diagnoses the issue.

### 3. **Refactoring with Confidence**
Before touching `AuthService`, agent checks:
- `query_blast_radius("AuthService", depth=2)` → sees all 47 dependents
- `validate_constraints()` → ensures 6 security constraints are met
- Safe to refactor.

### 4. **Code Review**
PR changes `PaymentProcessor`:
CI runs `graph-check` → fails because idempotency constraint is violated.
Reviewer comments: "See the constraint attached to PaymentProcessor?"
Developer updates thought, adds acknowledgment → CI passes.

### 5. **Living Documentation**
Agent runs: `generate_wiki_from_graph()` → outputs Markdown docs.
When you change code, the graph updates, docs auto-update. No stale documentation.

## Testing

Run all tests:
```bash
npm run test:python        # Python: 38 tests
npm run test               # TypeScript: (add tests as needed)
```

Run tests in watch mode:
```bash
npm run test:python -- --watch
```

## Development

### Setup
```bash
npm install
npm run build
npm run watch    # Live reload on source changes
```

### Debug Extension
1. Press F5 to launch Extension Development Host
2. Open a Python/TypeScript file
3. Run commands via Command Palette (Cmd+Shift+P)
4. Check Debug Console for logs

### Debug Python Server
In `.vscode/launch.json`, add:
```json
{
  "name": "Python MCP Server",
  "type": "python",
  "request": "attach",
  "port": 5678,
  "host": "localhost"
}
```

Then run:
```bash
cd src/server && python -m debugpy.adapter --log-dir /tmp/debugpy_logs
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for:
- Development environment setup
- Testing guidelines
- PR process
- Code style (ESLint + Ruff)

## Roadmap

### Phase 1 ✅ DONE
- Foundation: SQLite schema, AST indexing, drift detection

### Phase 2 ✅ DONE
- Timestamps on thoughts
- Agent forcing tool (`edit_code_with_thought`)
- MCP tool visibility in Copilot

### Phase 3 🚀 IN PROGRESS
- **Hive Mind**: Git-tracked graph serialization
- **Blast Radius**: Dependency analysis with `query_blast_radius()`
- **Semantic CI**: Constraint validation + `graph-check` CLI
- **Marketplace Ready**: Docs, CI/CD, professional extension metadata

### Phase 4 (Future)
- **Living Documentation**: Auto-generate wikis from graph
- **Onboarding Chatbot**: Specialized repo archaeology agent
- **Collaborative Thoughts**: Real-time sync + conflict resolution
- **Visualization Dashboard**: DAG rendering in webview

## Support

- **Documentation**: [docs/](./docs/)
- **GitHub Issues**: [Report bugs](https://github.com/yourusername/shadowgraph/issues)
- **Discussions**: [Ask questions](https://github.com/yourusername/shadowgraph/discussions)

## License

MIT © 2026 ShadowGraph Contributors

---

**ShadowGraph is not a code editor plugin. It's a semantic memory system for teams.**

"Don't just commit code. Commit understanding."
