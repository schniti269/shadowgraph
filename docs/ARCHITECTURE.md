# ShadowGraph Architecture

This document describes the internal design of ShadowGraph for contributors and maintainers.

## System Overview

```
┌─────────────────────────── VS Code Process ──────────────────────────┐
│                                                                       │
│  ┌────────────────────────── Extension Host ────────────────────┐  │
│  │                                                               │  │
│  │  extension.ts (Activation)                                   │  │
│  │  ├─ Initialize SQL.js database reader                        │  │
│  │  ├─ Setup Python venv + pip install requirements            │  │
│  │  ├─ Register MCP server definition provider                 │  │
│  │  ├─ Watch .vscode/shadow.db for changes                     │  │
│  │  ├─ Watch .shadow/graph.jsonl for git merges                │  │
│  │  └─ Register CodeLens, Decorations, Commands                │  │
│  │                                                               │  │
│  │  UI Layer                                                     │  │
│  │  ├─ codelens.ts → Show thought count above symbols           │  │
│  │  ├─ decorations.ts → Show stale anchor warnings              │  │
│  │  ├─ blast-radius-view.ts → TreeView of dependencies          │  │
│  │  └─ commands.ts → Handle user commands                       │  │
│  │                                                               │  │
│  │  Data Access                                                  │  │
│  │  ├─ database.ts → SQL.js wrapper (reads)                    │  │
│  │  └─ git-integration.ts → Serialization/deserialization       │  │
│  │                                                               │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                              │ MCP (stdio)                          │
│                              │ JSON-RPC over pipe                   │
│                              ↓                                      │
│  ┌────────────────────── Python Subprocess ──────────────────────┐  │
│  │ (spawned and managed by extension.ts)                        │  │
│  │                                                               │  │
│  │  main.py (FastMCP Server)                                    │  │
│  │  ├─ Listens on stdin/stdout                                  │  │
│  │  ├─ Exposes 8 MCP tools:                                    │  │
│  │  │  ├─ index_file()                                          │  │
│  │  │  ├─ add_thought()                                         │  │
│  │  │  ├─ get_context()                                         │  │
│  │  │  ├─ edit_code_with_thought()                              │  │
│  │  │  ├─ check_drift()                                         │  │
│  │  │  ├─ query_blast_radius() ⭐ NEW                           │  │
│  │  │  ├─ add_constraint() ⭐ NEW                               │  │
│  │  │  └─ validate_constraints() ⭐ NEW                         │  │
│  │  ├─ Logging to stderr (never stdout)                         │  │
│  │  └─ CLI mode support (main.py --cli <cmd>)                   │  │
│  │                                                               │  │
│  │  AST Engine                                                   │  │
│  │  ├─ indexer.py → tree-sitter parsing, symbol extraction      │  │
│  │  ├─ drift.py → AST hash comparison, staleness detection      │  │
│  │  └─ constraints.py ⭐ NEW → constraint validation            │  │
│  │                                                               │  │
│  │  Data Layer                                                   │  │
│  │  ├─ database.py → SQLite operations (writes)                 │  │
│  │  ├─ schema.sql → DDL (tables, indexes)                       │  │
│  │  ├─ serializer.py ⭐ NEW → SQLite → JSONL                    │  │
│  │  └─ deserializer.py ⭐ NEW → JSONL → SQLite                  │  │
│  │                                                               │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                              │ SQLite                              │
│                              ↓                                     │
└──────────────────────────────────────────────────────────────────────┘
                              .vscode/shadow.db (WAL mode)
                              .shadow/graph.jsonl (git-tracked)
```

## Core Components

### 1. Extension (`src/client/`)

#### `extension.ts`
**Responsibility**: Initialization, lifecycle management, MCP registration

```typescript
export async function activate(context: vscode.ExtensionContext) {
  1. Initialize SQL.js database reader
  2. Ensure Python environment (venv + pip install)
  3. Register MCP server definition provider with VS Code
  4. Register CodeLens provider
  5. Register decoration manager
  6. Register commands (index, check drift, show thoughts, etc.)
  7. Watch .vscode/shadow.db for changes → refresh UI
  8. Watch .shadow/graph.jsonl for changes → reload graph
}
```

**Key Pattern**: MCP server definition provider returns a `McpStdioServerDefinition` with:
```typescript
new McpStdioServerDefinition(
  'ShadowGraph Tools',              // Label (string)
  pythonInfo.pythonPath,            // Command (string)
  [serverScript],                   // Args (string[])
  { env: { SHADOW_DB_PATH, ... } }  // Options
)
```

#### `database.ts`
**Responsibility**: SQL.js wrapper for reading database

```typescript
class ShadowDatabase {
  async initialize() {
    // Load sql.js WASM binary
    // Open .vscode/shadow.db (SQLite file)
    // Verify schema, create tables if missing
  }

  getThoughtsForSymbol(file, symbol) {
    // Query: SELECT n.* FROM nodes n
    //        JOIN edges e ON e.target_id = n.id
    //        WHERE n.type = 'THOUGHT' AND ...
    //        ORDER BY n.created_at DESC
  }

  getStaleAnchors(file) {
    // Query: SELECT a.* FROM anchors a
    //        WHERE a.status = 'STALE'
  }
}
```

**Key Pattern**: Schema migration with try/catch fallback
```typescript
try {
  // Try new schema with created_at column
  const stmt = db.prepare(`SELECT ... n.created_at ...`);
} catch (err) {
  // Fall back to old schema without created_at
  const stmt = db.prepare(`SELECT ... FROM nodes n ...`);
}
```

#### `codelens.ts`
**Responsibility**: Show thought counts above code symbols

```typescript
class ShadowCodeLensProvider implements vscode.CodeLensProvider {
  provideCodeLenses(document) {
    // Regex: /^\s*(async\s+)?function\s+(\w+)|^\s*class\s+(\w+)/gm
    // For each match: query database for linked thoughts
    // Return CodeLens("🧠 N thoughts", showThoughts)
  }
}
```

#### `decorations.ts`
**Responsibility**: Show stale anchor warnings in gutter

```typescript
class StaleDecorationManager {
  async refresh() {
    // Get all stale anchors for current file
    // Create decoration range for each stale anchor
    // Apply decorations with stale.svg icon
  }
}
```

#### `commands.ts`
**Responsibility**: Handle user commands

Commands:
- `shadowgraph.initialize` → Create database
- `shadowgraph.indexCurrentFile` → Spawn Python CLI
- `shadowgraph.checkDrift` → Spawn Python CLI, show stale symbols
- `shadowgraph.showThoughts` → Display thoughts for symbol
- `shadowgraph.addThought` → Insert thought (via Python CLI)
- `shadowgraph.showStatus` → Display config + debug info
- `shadowgraph.runDiagnostics` → Verify Python + packages
- `shadowgraph.analyzeBlastRadius` ⭐ NEW → Open blast radius view

#### `blast-radius-view.ts` ⭐ NEW
**Responsibility**: TreeView provider for dependency DAG

```typescript
class BlastRadiusProvider implements vscode.TreeDataProvider {
  async getChildren(element?: Node) {
    if (!element) {
      // Return root: the query origin
    } else {
      // Return dependencies/dependents of element
    }
  }

  async getTreeItem(element: Node) {
    // Create TreeItem with:
    // - Icon (color-coded by stale status)
    // - Label (symbol name)
    // - Collapsible (has deps)
    // - Commands (jump to code, show context)
  }
}
```

#### `git-integration.ts` ⭐ NEW
**Responsibility**: Watch `.shadow/graph.jsonl`, auto-merge on pull

```typescript
class GitIntegration {
  async loadGraphFromJSON() {
    // Read .shadow/graph.jsonl
    // Deserialize JSONL back to SQLite
    // Merge strategy: LWW (last-write-wins based on timestamps)
  }

  async watchForChanges() {
    // FileSystemWatcher on .shadow/graph.jsonl
    // On change: loadGraphFromJSON + refresh UI
  }
}
```

#### `types.ts`
**Responsibility**: Shared TypeScript interfaces

```typescript
interface ThoughtRow {
  id: string;
  content: string;
  created_at: string; // ISO 8601
}

interface AnchorRow {
  node_id: string;
  file_path: string;
  symbol_name: string; // Prefixed: "function:foo"
  ast_hash: string;
  status: 'VALID' | 'STALE';
}

interface BlastRadiusNode {
  symbol: string;
  type: string; // CODE_BLOCK | THOUGHT | CONSTRAINT
  stale: boolean;
  thoughts: ThoughtRow[];
  dependencies: BlastRadiusNode[];
  dependents: BlastRadiusNode[];
}
```

### 2. Python MCP Server (`src/server/`)

#### `main.py`
**Responsibility**: FastMCP server, exposes 8 tools

```python
@mcp.tool()
def index_file(file_path: str) -> str:
    """Index file, extract symbols, compute hashes, store in DB"""
    symbols = do_index_file(file_path)
    for sym in symbols:
        node_id = f"code:{file_path}:{sym['symbol_name']}"
        db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        db.upsert_anchor(node_id, file_path, sym['symbol_name'], sym['ast_hash'], ...)
    return JSON(indexed_symbols)

@mcp.tool()
def query_blast_radius(symbol_name: str, depth: int = 2) -> str:
    """Recursively retrieve dependencies, dependents, thoughts"""
    sql = """
    WITH RECURSIVE neighborhood AS (
        SELECT id, type, content, 0 as level, 'ORIGIN' as relation
        FROM nodes WHERE symbol_name = ?
        UNION ALL
        -- Outgoing edges (dependencies)
        SELECT n.id, ..., nb.level + 1, e.relation
        FROM nodes n JOIN edges e ON e.target_id = n.id
        WHERE nb.level < ?
        UNION ALL
        -- Incoming edges (dependents)
        SELECT n.id, ..., nb.level + 1, 'IMPACTS'
        FROM nodes n JOIN edges e ON e.source_id = n.id
        WHERE nb.level < ?
    )
    SELECT * FROM neighborhood
    """
    return JSON(recursive_graph)

@mcp.tool()
def add_constraint(symbol_name: str, rule_text: str, severity: str) -> str:
    """Define a constraint that code must satisfy"""
    constraint_id = f"constraint:{uuid4()}"
    db.upsert_node(constraint_id, "CONSTRAINT", rule_text)
    db.add_edge(f"code:..:{symbol_name}", constraint_id, "REQUIRED_BY")
    return JSON(confirmation)

@mcp.tool()
def validate_constraints(file_path: str) -> str:
    """Check if modified code violates constraints"""
    stale_anchors = db.get_stale_anchors_for_file(file_path)
    violations = []
    for anchor in stale_anchors:
        constraints = db.get_constraints_for_symbol(anchor.symbol_name)
        violations.extend([...])
    return JSON(violations)
```

**CLI Mode** (for extension commands):
```bash
python main.py --cli index_file /path/to/file.py
python main.py --cli check_drift /path/to/file.py
```

#### `database.py`
**Responsibility**: SQLite CRUD operations

```python
class ShadowDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        # Execute schema.sql

    def upsert_node(self, node_id: str, node_type: str, content: str):
        # INSERT OR REPLACE INTO nodes
        # Automatically sets created_at if new

    def upsert_anchor(self, node_id: str, file_path: str, symbol_name: str, ...):
        # INSERT OR REPLACE INTO anchors
        # symbol_name is PREFIXED: "function:foo"

    def add_edge(self, source_id: str, target_id: str, relation: str):
        # INSERT OR IGNORE INTO edges

    def get_thoughts_for_symbol(self, file_path: str, symbol_name: str):
        # SELECT n.* FROM nodes n
        # JOIN edges e ON e.target_id = n.id
        # WHERE symbol_name = ? AND n.type = 'THOUGHT'
        # ORDER BY n.created_at DESC
```

#### `indexer.py`
**Responsibility**: Tree-sitter AST parsing, symbol extraction, hash computation

```python
def index_file(file_path: str) -> list[dict]:
    """Parse file, extract all top-level functions/classes"""
    parser = get_parser(language)
    tree = parser.parse(source_code)

    symbols = []
    for node in tree.root_node.children:
        if node.type in ['function_definition', 'class_definition']:
            name = extract_symbol_name(node)
            prefix = 'function' if 'function' in node.type else 'class'
            full_name = f"{prefix}:{name}"  # PREFIXED
            ast_hash = compute_ast_hash(node.text)  # Whitespace-stripped SHA256
            symbols.append({
                'symbol_name': full_name,
                'content': node.text,
                'ast_hash': ast_hash,
            })

    # ⭐ NEW: Extract imports + function calls as DEPENDS_ON edges
    for import_node in find_imports(tree):
        source = f"code:{file}:{current_function}"
        target = f"code:{imported_file}:{imported_func}"
        edges.append(("DEPENDS_ON", source, target))

    return symbols

def compute_ast_hash(node_text: str) -> str:
    """SHA256 of whitespace-stripped code"""
    normalized = re.sub(r"\s+", "", node_text)
    return hashlib.sha256(normalized.encode()).hexdigest()
```

**Key Pattern**: Symbol names are ALWAYS PREFIXED
- Database stores: `"function:login"`, `"class:AuthService"`
- This is added by indexer during extraction
- MCP tools expect prefixed format when querying

#### `drift.py`
**Responsibility**: Detect code changes since last indexing

```python
def check_drift(db, file_path: str) -> list[dict]:
    """Compare current AST hashes vs stored"""
    current_symbols = index_file(file_path)
    stored_anchors = db.get_anchors_for_file(file_path)

    stale = []
    for stored in stored_anchors:
        current = find_by_name(current_symbols, stored.symbol_name)
        if not current or current['ast_hash'] != stored.ast_hash:
            db.mark_stale(stored.node_id, file_path, stored.symbol_name)
            stale.append({
                'symbol': stored.symbol_name,
                'reason': 'Code changed',
            })

    return stale
```

#### `serializer.py` ⭐ NEW
**Responsibility**: Export SQLite graph to JSONL

```python
def serialize_to_jsonl(db, output_file: str):
    """Write nodes and edges as JSONL (one per line)"""
    with open(output_file, 'w') as f:
        for node in db.get_all_nodes():
            # Add sync_id for conflict tracking
            node['sync_id'] = hashlib.sha256(
                (node['id'] + node['content']).encode()
            ).hexdigest()
            f.write(json.dumps(node) + '\n')

        for edge in db.get_all_edges():
            edge['sync_id'] = hashlib.sha256(
                (edge['source_id'] + edge['target_id']).encode()
            ).hexdigest()
            f.write(json.dumps(edge) + '\n')
```

#### `deserializer.py` ⭐ NEW
**Responsibility**: Import JSONL, merge with existing DB

```python
def deserialize_from_jsonl(db, input_file: str, merge_strategy='lww'):
    """Load JSONL, merge with existing DB using merge strategy"""
    incoming = {}
    with open(input_file) as f:
        for line in f:
            obj = json.loads(line)
            incoming[obj['id']] = obj

    for id, incoming_obj in incoming.items():
        existing = db.get_node(id)
        if not existing:
            db.upsert_node(...)  # New node
        elif merge_strategy == 'lww':
            # Last-write-wins: compare timestamps
            if incoming_obj['created_at'] > existing['created_at']:
                db.upsert_node(...)  # Update
```

#### `constraints.py` ⭐ NEW
**Responsibility**: Constraint node CRUD + validation

```python
class ConstraintValidator:
    def add_constraint(self, symbol_name: str, rule_text: str, severity: str):
        """Create CONSTRAINT node"""
        constraint_id = f"constraint:{uuid4()}"
        db.upsert_node(constraint_id, "CONSTRAINT", rule_text)
        code_node_id = f"code:*:{symbol_name}"  # Applies to all files
        db.add_edge(code_node_id, constraint_id, "REQUIRED_BY")

    def validate(self, file_path: str) -> list[dict]:
        """Check stale symbols against constraints"""
        stale = check_drift(db, file_path)
        violations = []
        for symbol in stale:
            constraints = db.get_constraints_for_symbol(symbol)
            for constraint in constraints:
                if constraint['severity'] in ['critical', 'high']:
                    violations.append({
                        'constraint': constraint['id'],
                        'symbol': symbol,
                        'status': 'VIOLATED',
                    })
        return violations
```

#### `schema.sql`
**Responsibility**: DDL for all tables

```sql
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL, -- CODE_BLOCK | THOUGHT | CONSTRAINT | REQUIREMENT
    content TEXT,
    vector BLOB, -- Future: embeddings for semantic search
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_id TEXT -- For conflict tracking in Hive Mind
);

CREATE TABLE IF NOT EXISTS anchors (
    node_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    symbol_name TEXT NOT NULL, -- PREFIXED: "function:foo"
    ast_hash TEXT NOT NULL,
    start_line INTEGER,
    status TEXT DEFAULT 'VALID', -- VALID | STALE
    FOREIGN KEY (node_id) REFERENCES nodes(id),
    UNIQUE(file_path, symbol_name)
);

CREATE TABLE IF NOT EXISTS edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL, -- HAS_THOUGHT | DEPENDS_ON | REQUIRED_BY | IMPACTS
    sync_id TEXT, -- For conflict tracking
    PRIMARY KEY (source_id, target_id, relation),
    FOREIGN KEY (source_id) REFERENCES nodes(id),
    FOREIGN KEY (target_id) REFERENCES nodes(id)
);

CREATE INDEX idx_anchors_file ON anchors(file_path);
CREATE INDEX idx_anchors_symbol ON anchors(symbol_name);
CREATE INDEX idx_edges_target ON edges(target_id);
```

## Key Design Decisions

### 1. **Symbol Naming Convention**
- Database stores **PREFIXED** symbol names: `"function:login"`, `"class:AuthService"`
- Added by indexer during extraction (`get_symbol_type_prefix()`)
- All MCP tools expect prefixed format in queries
- Benefits: Type information in one place, no ambiguity

### 2. **AST Hash Stability**
- Computed as SHA256 of **whitespace-stripped** code
- Immune to formatting changes (spaces, newlines, indentation)
- Drift detection compares hash values, not text
- Benefits: Refactoring without "stale" false positives

### 3. **WAL Mode**
- SQLite `PRAGMA journal_mode=WAL`
- Safe concurrent reads (TS via sql.js) + writes (Python via sqlite3)
- Benefits: No locking issues between extension UI and MCP server

### 4. **Timestamps on All Nodes**
- Every node has `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- Enables temporal queries ("Show me what changed in last hour")
- Used for LWW merge strategy in Hive Mind
- Benefits: Full auditability, conflict resolution

### 5. **Serialization Format: JSONL**
- One node/edge per line (newline-delimited JSON)
- Diffs cleanly in git (one object per line)
- Mergeable: conflict markers mark entire objects
- Benefits: Human-readable, version control friendly

### 6. **Recursive Dependency Queries**
- `query_blast_radius()` uses SQL recursive CTEs
- Follows edges up to `depth` hops
- Returns full node details (type, content, stale flag, thoughts)
- Benefits: Agents get complete context for dependencies

### 7. **Constraint Severity Levels**
- `critical`: Blocks CI, must be addressed
- `high`: Warning in CI, doesn't fail pipeline
- `medium` / `low`: Informational, logged only
- Benefits: Nuanced enforcement, prevents over-alerting

### 8. **No Native Dependencies**
- Extension: Pure TypeScript + VS Code API (uses sql.js WASM)
- Python: Only pure-Python packages (mcp, tree-sitter, sqlite3)
- Benefits: Zero compilation, works on all platforms

## Data Flow: Example Workflow

### Scenario: Developer adds a thought

1. **User action**: Command Palette → "ShadowGraph: Add Thought"
2. **Extension**: Opens input dialog, gets symbol from cursor position
3. **Extension**: Spawns `python main.py --cli add_thought <file> <symbol> <thought>`
4. **Python**:
   - Creates THOUGHT node with `created_at` timestamp
   - Creates HAS_THOUGHT edge from CODE_BLOCK to THOUGHT
   - Commits transaction
5. **Extension**: Watches `.vscode/shadow.db` for change
6. **Extension**: Reloads database, refreshes CodeLens/Decorations
7. **UI**: Updates to show new thought count above symbol

### Scenario: Agent queries blast radius

1. **Agent**: Calls MCP tool `query_blast_radius("PaymentProcessor", depth=2)`
2. **Python**: Executes recursive query starting from `PaymentProcessor` node
3. **Python**: Returns:
   - Origin node (PaymentProcessor) + thoughts
   - Level 1: Direct dependencies + dependents
   - Level 2: Transitive dependencies + dependents
   - Stale flags on each anchor
4. **Agent**: Renders DAG in chat, identifies stale dependency "CurrencyConverter changed 2h ago"
5. **Agent**: Queries `get_context("CurrencyConverter")` to see what changed
6. **Agent**: Diagnoses root cause of error

### Scenario: Serializing graph for git

1. **User**: Runs `Command Palette → ShadowGraph: Export to Git`
2. **Extension**: Calls `serializer.serialize_to_jsonl(.vscode/shadow.db, .shadow/graph.jsonl)`
3. **Python**: Reads all nodes/edges, assigns `sync_id` (hash of id + content)
4. **Python**: Writes to `.shadow/graph.jsonl` (one JSON per line)
5. **User**: `git add .shadow/graph.jsonl && git commit`
6. **Team member**: Pulls repo
7. **Extension**: Watches `.shadow/graph.jsonl`, calls `deserializer.deserialize_from_jsonl()`
8. **Python**: Reads JSONL, merges with local `.vscode/shadow.db` using LWW strategy
9. **Extension**: Reloads UI, team member sees original developer's thoughts

## Testing Strategy

### Unit Tests (Python)
- **test_database.py**: CRUD operations, schema migrations
- **test_indexer.py**: Symbol extraction, hash computation, stability
- **test_drift.py**: Staleness detection
- **test_serializer.py**: JSONL serialization fidelity
- **test_deserializer.py**: JSONL deserialization + merge conflicts
- **test_constraints.py**: Constraint creation, validation, violations
- **test_blast_radius.py**: Recursive queries, depth limits, filtering

### Integration Tests (TypeScript)
- Extension activation (venv setup, database init)
- MCP registration (tools appear in Copilot)
- CodeLens rendering (thoughts counted correctly)
- Git integration (JSONL load/merge)

### E2E Tests
- Full workflow: Index → Add Thought → Serialize → Pull → See Thought
- Constraint workflow: Add Constraint → Modify Code → Run graph-check → Fail
- Blast Radius workflow: Query → See Dependencies → Debug Error

## Performance Considerations

### Database Queries
- **Indexes**: On `file_path`, `symbol_name`, `target_id` for fast lookups
- **Recursive CTEs**: Limited depth (default 2) to prevent quadratic blowup
- **Pagination**: Future feature for large graphs (use LIMIT/OFFSET)

### UI Refresh
- **Debounced**: Batch multiple .vscode/shadow.db changes
- **Lazy**: CodeLens queries only visible symbols
- **Cached**: Reuse database connection while file is open

### Serialization
- **Streaming**: JSONL is line-oriented, process one node at a time
- **Diff-friendly**: Each node/edge is independent, minimal diffs on change

## Future Enhancements

1. **Vector Embeddings**: Use `nodes.vector` column for semantic search
2. **Bulk Operations**: Export/import entire graphs without git
3. **Real-time Collaboration**: WebSocket sync for multi-user editing
4. **Visualization Dashboard**: Webview for DAG rendering (Mermaid/Cytoscape)
5. **Living Documentation**: Auto-generate wikis from constraint + thought graph
6. **Agent Learning**: Store successful diagnoses as training data

---

**Last Updated**: 2026-02-15 (Phase 3)
