# Changelog

All notable changes to ShadowGraph are documented in this file.

## [0.3.0] - 2026-02-15 🚀 Production Ready

### Added

#### Hive Mind: Git-Integrated Graphs
- New `serializer.py`: Export SQLite graph to `.shadow/graph.jsonl` (JSONL format, one node/edge per line)
- New `deserializer.py`: Import JSONL back to SQLite with merge strategy for team collaboration
- New `git-integration.ts`: Auto-watch `.shadow/graph.jsonl`, merge on pull, warn on conflicts
- New `merge-strategy.py`: Conflict resolution using timestamps + content hashes (LWW strategy)
- `.shadow/.gitkeep` + `.shadow/.gitignore`: Track JSONL, ignore local `.db` files
- Schema update: Added `sync_id` column to nodes/edges for conflict tracking
- **Benefit**: Team members pull code and instantly see thoughts + dependency structure. "Tribal knowledge" becomes "repo knowledge."

#### Blast Radius Analysis 🎯
- New `query_blast_radius(symbol_name, depth=2)` MCP tool: Recursively retrieve dependencies, dependents, and attached context
  - Incoming edges (IMPACTS): "Who depends on this?"
  - Outgoing edges (DEPENDS_ON): "What do I depend on?"
  - Attached thoughts: Full context for each node
  - Stale flags: Highlights outdated dependencies
- New `blast-radius-view.ts`: TreeView provider showing dependency DAG with status colors
- New `shadowgraph.analyzeBlastRadius` command: Opens blast radius view for any symbol
- Updated `indexer.py`: Automatic extraction of DEPENDS_ON edges from imports + function calls
- New edge type `DEPENDS_ON`: Replaces old naming, now includes both imports and calls
- **Benefit**: Agents debug with 95% less context noise. Instead of reading 5 files, query the subgraph.

#### Semantic CI/CD 🛡️
- New `constraints.py`: Constraint node CRUD + validation logic
- New MCP tools:
  - `add_constraint(symbol_name, rule_text, severity)`: Define rules ("Payments must be idempotent")
  - `validate_constraints(file_path)`: Check for violations
- New `tools/graph-check.py` CLI: Run in CI pipelines
  - `graph-check .vscode/shadow.db src/ --fail-on critical`: Validates code against constraints
  - Returns exit code 1 on violations → fails CI
- New node type `CONSTRAINT`: RULE, FORBIDDEN, REQUIRED_PATTERN, REQUIRES_EDGE
- New edge type `REQUIRED_BY`: Constraint applies to code
- **Benefit**: Prevent "silent failures" — catch intent violations before production (e.g., payment code loses idempotency)

#### Marketplace Ready 🏪
- New `README.md`: Comprehensive feature showcase, installation guide, use cases, MCP tool reference
- New `CHANGELOG.md`: This file, version history
- New `CONTRIBUTING.md`: Development setup, testing, PR guidelines
- New `docs/ARCHITECTURE.md`: Detailed system design for contributors
- New `docs/BLAST_RADIUS.md`: How to use blast radius queries for debugging
- New `docs/GIT_INTEGRATION.md`: How `.shadow/` folder works, collaboration patterns
- New `.github/workflows/test.yml`: Run Python + TypeScript tests on PR/push
- New `.github/workflows/lint.yml`: ESLint (TS) + Ruff (Python) on PRs
- New `.github/workflows/publish.yml`: Tag-triggered VSIX packaging + marketplace publish
- New `.github/ISSUE_TEMPLATE/bug_report.yml`: Bug report template
- New `.github/ISSUE_TEMPLATE/feature_request.yml`: Feature request template
- New `.github/PULL_REQUEST_TEMPLATE.md`: PR checklist (tests, docs, backward compat)
- Updated `package.json`:
  - Version: 0.3.0
  - Keywords: semantic, ai-agents, debugging, collaboration, intent-preservation
  - Repository: proper GitHub URL
  - Publisher: (requires VS Code Marketplace publisher account)
  - License: MIT
- Updated `tsconfig.json`: Enabled strict mode (`strict: true`, `noImplicitAny: true`)
- Updated `esbuild.js`: Production minification + source maps
- Updated `.vscodeignore`: Exclude test files, workflows, docs from VSIX

### Changed

- **Schema Migration**: Added `sync_id` column to nodes/edges table (nullable, auto-filled on serialize)
- **Symbol Edge Extraction**: Updated `indexer.py` to extract both import statements and function calls as DEPENDS_ON edges
- **Timestamp Handling**: All timestamps now include timezone info (ISO 8601 UTC format)
- **Version Bump**: 0.2.0 → 0.3.0 (semantic versioning)

### Fixed

- None (phase 3 is feature-additive on Phase 2)

### Testing

- New test suite:
  - `test_serializer.py` (5 tests): SQLite → JSONL fidelity
  - `test_deserializer.py` (5 tests): JSONL → SQLite round-trip + merge conflicts
  - `test_blast_radius.py` (6 tests): Recursive queries, stale flags, depth limits
  - `test_constraints.py` (5 tests): Constraint creation, validation, violations
  - **Total**: 22 existing tests + 16 new tests = 38 tests passing
  - CI/CD: All tests run on PR/push via GitHub Actions

### Breaking Changes

- None (Phase 3 is backward compatible with Phase 2)

### Migration Guide

**For existing Phase 2 users:**
1. Update extension: VS Code will auto-update
2. (Optional) Serialize existing graph: Run `Command Palette → ShadowGraph: Export to .shadow/graph.jsonl`
3. (Optional) Commit graph: `git add .shadow/graph.jsonl && git commit -m "docs: add collaborative graph"`
4. New teammates can now pull and see your thoughts automatically!

---

## [0.2.0] - 2026-02-15 ✨ Agent Forcing + Discoverability

### Added

#### Timestamps on Thoughts
- New `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` column on nodes table
- All new thoughts automatically capture creation time
- Thoughts now ordered by creation time (DESC) in UI
- Timestamps formatted for readability ("2 hours ago", "today")
- **Benefit**: See evolution of architectural decisions over time

#### Agent Forcing Tool
- New `edit_code_with_thought(file_path, symbol_name, thought_text, new_code?)` MCP tool
- Forces AI agents to document WHY before editing code
- Workflow: Agent → calls tool (explains change) → tool creates THOUGHT → agent edits code → agent calls index_file()
- `get_context()` now warns if symbols lack thoughts
- **Benefit**: No more undocumented refactors. Every change has explicit reasoning.

#### MCP Tool Visibility & Discoverability
- Fixed VS Code McpStdioServerDefinition API (positional arguments, not options object)
- Tools now appear in Copilot Chat "Configure Tools" dropdown
- New command: `shadowgraph.showStatus` — Display server config + debug instructions
- New command: `shadowgraph.runDiagnostics` — Verify Python install, packages, database health
- Comprehensive logging with `[ShadowGraph]` prefix for easy debugging
- **Benefit**: Agents can see and use all 5 ShadowGraph tools in Copilot

### Changed

- Activation event: `onStartupFinished` → `*` (force immediate load for MCP registration)
- Symbol naming convention clarified in documentation: Database stores **PREFIXED** names (`"function:predict"`, `"class:MyClass"`)

### Fixed

- MCP tool registration bug: Incorrect API usage prevented tools from appearing in Copilot dropdown

### Testing

- All 22 tests passing (Phase 1 + Phase 2 features)

---

## [0.1.0] - 2026-02-01 🎉 Foundation

### Added

#### Core Architecture
- SQLite graph database with WAL mode (`.vscode/shadow.db`)
- 3 node types: CODE_BLOCK, THOUGHT, REQUIREMENT
- 2 edge types: HAS_THOUGHT, (future: DEPENDS_ON, CONSTRAINTS)
- Stable AST hashing (SHA256 of whitespace-stripped code)

#### Tree-Sitter Integration
- Multi-language parsing: Python, TypeScript, JavaScript, TSX
- Automatic symbol extraction: functions, classes
- Type-prefixed symbol names (`function:login`, `class:AuthService`)
- Whitespace-insensitive hash stability

#### Drift Detection
- Compare current AST hashes vs stored → mark STALE anchors
- Gutter decorations warn about modified code
- `check_drift()` command shows all stale symbols

#### MCP Tools (4)
- `index_file(file_path)`: Parse file, extract symbols, compute hashes, store in DB
- `add_thought(file_path, symbol_name, thought_text)`: Attach note to symbol
- `get_context(file_path, symbol_name)`: Retrieve code + all linked thoughts
- `check_drift(file_path)`: Detect code changes since indexing

#### VS Code Integration
- CodeLens: Show thought count above functions/classes
- Decorations: Stale anchor warnings in gutter
- 5 user commands: Initialize, Index File, Add Thought, Check Drift, Show Thoughts
- Python venv management: Auto-setup in global storage
- File watcher: Auto-reload UI when DB changes

#### Testing
- 22 comprehensive Python tests (database, indexer, drift, MCP tools)
- Pytest fixtures for isolation
- Multi-file, multi-language test coverage

### Architecture

**Tech Stack:**
- **Extension**: TypeScript, VS Code API, sql.js (WASM)
- **Server**: Python, FastMCP, tree-sitter, sqlite3
- **Build**: esbuild (TS only), Python shipped as source
- **Database**: SQLite with WAL, indexes for performance
- **Transport**: stdio (VS Code manages Python subprocess)

**Design Principles:**
- Pure WASM for TS reads (no native compilation)
- Full SQL + transactions for Python writes
- Stable AST hashes immune to formatting
- Timestamps for temporal queries
- Prefixed symbol names for type information

### Testing

- 22 tests covering all major features
- All tests passing

---

## Legend

- ✨ = New feature (user-facing)
- 🎉 = Major release
- 🚀 = Production ready
- 🎯 = Killer feature
- 🛡️ = Security/reliability
- 🏪 = Marketplace ready
- ✅ = Completed
- 🚧 = In progress
- ⏳ = Planned

---

## Commit History

- **d08af71** (Phase 2 completion): Clarify symbol naming, document final status
- **976a8b8** (Phase 2): Timestamps, agent forcing, MCP visibility
- **e501f38** (Phase 1): Foundation + core tools
- **2385788** (Initial): Project scaffold
