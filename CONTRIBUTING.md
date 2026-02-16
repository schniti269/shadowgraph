# Contributing to ShadowGraph

Thanks for your interest in contributing to ShadowGraph! This guide will help you get set up and start contributing.

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Running Tests](#running-tests)
4. [Making Changes](#making-changes)
5. [Submitting PRs](#submitting-prs)
6. [Code Style](#code-style)
7. [Debugging](#debugging)

## Development Setup

### Prerequisites

- **Node.js** 18+ (for TypeScript extension)
- **Python** 3.10+ (for MCP server)
- **Git** (obviously)
- **VS Code** (for testing the extension)

### Step 1: Clone and Install

```bash
git clone https://github.com/yourusername/shadowgraph.git
cd shadowgraph

# Install Node dependencies
npm install

# Create Python virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install Python dependencies
pip install -r requirements.txt
pip install -e .          # Install in editable mode for development
```

### Step 2: Build and Test

```bash
# Build extension
npm run build

# Run Python tests
npm run test:python

# Watch for changes during development
npm run watch
```

### Step 3: Launch Extension Development Host

1. Open VS Code
2. Press **F5** to launch Extension Development Host
3. Open a Python or TypeScript file
4. Test commands via Command Palette (Cmd+Shift+P)

## Project Structure

```
shadowgraph/
├── src/
│   ├── client/                    # TypeScript Extension
│   │   ├── extension.ts           # Entry point
│   │   ├── database.ts            # SQL.js wrapper
│   │   ├── codelens.ts            # CodeLens provider
│   │   ├── decorations.ts         # Stale warnings
│   │   ├── commands.ts            # Command handlers
│   │   ├── blast-radius-view.ts   # TreeView provider
│   │   ├── git-integration.ts     # Graph serialization
│   │   ├── pythonSetup.ts         # venv management
│   │   └── types.ts               # Shared interfaces
│   │
│   └── server/                    # Python MCP Server
│       ├── main.py                # FastMCP server + CLI
│       ├── database.py            # SQLite operations
│       ├── schema.sql             # Database schema
│       ├── indexer.py             # AST parsing
│       ├── drift.py               # Staleness detection
│       ├── serializer.py          # JSONL export
│       ├── deserializer.py        # JSONL import + merge
│       ├── constraints.py         # Constraint validation
│       └── __init__.py
│
├── src/test/
│   ├── server/                    # Python tests
│   │   ├── conftest.py            # pytest fixtures
│   │   ├── test_database.py
│   │   ├── test_indexer.py
│   │   ├── test_drift.py
│   │   ├── test_main.py
│   │   ├── test_serializer.py
│   │   ├── test_deserializer.py
│   │   ├── test_constraints.py
│   │   └── test_blast_radius.py
│   │
│   └── client/                    # TypeScript tests (add as needed)
│       ├── database.test.ts
│       ├── extension.test.ts
│       └── codelens.test.ts
│
├── tools/
│   └── graph-check.py             # CLI for CI/CD
│
├── .shadow/
│   ├── graph.jsonl                # Serialized graph (git-tracked)
│   └── .gitignore
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── BLAST_RADIUS.md
│   └── GIT_INTEGRATION.md
│
├── icons/
│   ├── thought.svg
│   └── stale.svg
│
├── package.json
├── tsconfig.json
├── esbuild.js
├── requirements.txt
├── .vscodeignore
├── .gitignore
├── README.md
├── CHANGELOG.md
└── CONTRIBUTING.md (this file)
```

## Running Tests

### Python Tests

```bash
# Run all tests
npm run test:python

# Run specific test file
pytest src/test/server/test_indexer.py -v

# Run with coverage
pytest src/test/server --cov=src.server

# Watch mode (re-run on change)
pytest-watch src/test/server
```

### Test Organization

- **test_database.py**: CRUD operations, schema, transactions
- **test_indexer.py**: Symbol extraction, AST hashing
- **test_drift.py**: Staleness detection
- **test_main.py**: MCP tool execution
- **test_serializer.py**: JSONL export fidelity
- **test_deserializer.py**: JSONL import + merge conflicts
- **test_constraints.py**: Constraint creation and validation
- **test_blast_radius.py**: Recursive dependency queries

### Writing New Tests

**Template:**
```python
import pytest
from src.server.database import ShadowDB

def test_my_feature(tmp_db: ShadowDB):
    """Test description"""
    # Arrange
    db = tmp_db

    # Act
    result = db.some_operation()

    # Assert
    assert result == expected_value
```

**Use fixtures from conftest.py:**
- `tmp_db` — Temporary in-memory SQLite database
- `sample_python_file` — Test Python file with known symbols
- `sample_typescript_file` — Test TypeScript file

### TypeScript Tests (Recommended for New UI Features)

```bash
# Add Jest for testing
npm install --save-dev jest @types/jest ts-jest

# Create test
cat > src/test/client/my-feature.test.ts << 'EOF'
describe('MyFeature', () => {
  test('should do something', () => {
    expect(true).toBe(true);
  });
});
EOF

# Run
npm test
```

## Making Changes

### Before You Start

1. **Check existing issues/PRs**: Avoid duplicate work
2. **Discuss large changes**: Open an issue first for major features
3. **Keep scope small**: One feature per PR
4. **Update tests**: Every change needs test coverage

### Branch Naming

```bash
# Feature
git checkout -b feature/blast-radius-analysis

# Bug fix
git checkout -b fix/codelens-crash

# Documentation
git checkout -b docs/add-troubleshooting-guide

# Chore
git checkout -b chore/update-dependencies
```

### Commit Messages

```
Format: <type>(<scope>): <subject>

type: feat, fix, docs, style, refactor, test, chore
scope: client, server, tests, ci
subject: imperative, lowercase, no period

Example:
feat(server): add query_blast_radius MCP tool

Implement recursive dependency query for semantic debugging.
Supports depth parameter and returns full node context.

Closes #123
```

### Code Changes Checklist

- [ ] Write feature/fix code
- [ ] Add tests (aim for >80% coverage)
- [ ] Run tests locally: `npm run test:python`
- [ ] Update documentation if API changes
- [ ] Run linter: `npm run lint` (when available)
- [ ] Test manually in Extension Development Host (F5)

## Submitting PRs

### PR Checklist

```markdown
## Description
[Brief summary of changes]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
[Describe test scenario]

## Checklist
- [ ] Tests pass locally (`npm run test:python`)
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] No breaking changes (or documented if necessary)
- [ ] Commits are squashed/clean

## Related Issues
Closes #[issue number]
```

### PR Review Process

1. **Automated checks** (GitHub Actions):
   - Python tests (`pytest`)
   - TypeScript tests (when added)
   - Linting (ESLint + Ruff)

2. **Code review**:
   - At least 1 maintainer approval required
   - Feedback addressed before merge
   - Update CHANGELOG.md

3. **Merge and release**:
   - Squash-merge to main
   - Tag version: `git tag v0.X.Y`
   - Publish to VS Code Marketplace

## Code Style

### TypeScript

Use **ESLint** (when configured):

```bash
npm run lint
npm run lint --fix
```

**Rules to follow:**
- 2-space indentation
- Semicolons required
- Double quotes for strings
- No `any` types (use `unknown` + type guards)
- Use `const`/`let`, avoid `var`

### Python

Use **Ruff** for linting and formatting:

```bash
pip install ruff

# Check
ruff check src/server/

# Fix
ruff check --fix src/server/

# Format
ruff format src/server/
```

**Rules to follow:**
- 4-space indentation
- PEP 8 style guide
- Type hints required (Python 3.10+)
- Docstrings for all public functions
- Logging with structured format

### Example Python Function

```python
import logging

logger = logging.getLogger("shadowgraph")

def query_blast_radius(
    db: ShadowDB,
    symbol_name: str,
    depth: int = 2,
) -> dict[str, Any]:
    """
    Retrieve the semantic neighborhood of a symbol.

    Recursively finds dependencies (outgoing edges) and dependents
    (incoming edges) up to the specified depth.

    Args:
        db: ShadowDB instance
        symbol_name: e.g., "function:charge" or "class:AuthService"
        depth: Maximum edge hops to follow (default 2)

    Returns:
        Dictionary with keys: origin, dependencies, dependents, metadata

    Raises:
        ValueError: If symbol_name is not prefixed
        sqlite3.OperationalError: If database is corrupted
    """
    logger.debug(f"Querying blast radius for {symbol_name} at depth {depth}")

    if ":" not in symbol_name:
        raise ValueError("Symbol name must be prefixed (e.g., 'function:foo')")

    # Implementation...
```

## Debugging

### Debug Extension (TypeScript)

1. Set breakpoints in VS Code editor
2. Open Extension Development Host (F5)
3. Breakpoints will hit in host window
4. Use Debug Console to inspect variables

### Debug Python Server

```bash
# Terminal 1: Start debugger
cd src/server
python -m debugpy.adapter

# Terminal 2: Run extension (F5 in VS Code)
# Python debugger connects automatically

# Breakpoints in Python files will hit
```

### View Extension Logs

```bash
# Extension logs (TypeScript)
View → Output → ShadowGraph

# Server logs (Python)
View → Output → ShadowGraph Server
```

### Common Issues

**Issue**: "ModuleNotFoundError: No module named 'indexer'"
```bash
# Solution: Python path issue. Verify src/server/ is in sys.path
python -c "import sys; print(sys.path)"
```

**Issue**: "sql.js WASM binary not found"
```bash
# Solution: Rebuild extension
npm run build

# Check that dist/sql-wasm.wasm exists
ls dist/sql-wasm.wasm
```

**Issue**: ".vscode/shadow.db is locked"
```bash
# Solution: Extension or Python server is still running
# Kill all Python processes
pkill -f "python.*main.py"

# Restart extension
```

## Documentation

When adding features, update:

1. **README.md**: User-facing features
2. **CHANGELOG.md**: Version history
3. **docs/ARCHITECTURE.md**: Implementation details
4. **docs/BLAST_RADIUS.md**: Debugging features
5. **Code comments**: Complex algorithms or non-obvious patterns

### Doc Style

- **Markdown**: GitHub-flavored markdown
- **Code blocks**: Include language (```python, ```typescript)
- **Examples**: Real-world scenarios, not just API docs
- **Links**: Cross-reference related docs

## Performance Guidelines

### Python
- Prefer generator functions for large result sets
- Use `LIMIT` in SQL queries
- Index frequently queried columns
- Avoid `SELECT *`, specify columns

### TypeScript
- Debounce file watchers (wait 100ms for changes)
- Lazy-load heavy modules
- Cache database queries (5-minute TTL)
- Use `vscode.window.withProgress()` for long operations

## Release Process

1. **Update version** in `package.json`
2. **Update CHANGELOG.md** with new features
3. **Run full test suite**: `npm run test:python`
4. **Build extension**: `npm run build`
5. **Tag release**: `git tag v0.X.Y`
6. **Push tag**: `git push origin v0.X.Y`
7. **Publish** to VS Code Marketplace (CI/CD via GitHub Actions)

## Getting Help

- **Questions?** Open a discussion on GitHub
- **Found a bug?** [Report it](https://github.com/yourusername/shadowgraph/issues)
- **Want to discuss a feature?** Start an issue

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) (to be added).

---

**Thanks for contributing to ShadowGraph! 🎉**

**Last Updated**: 2026-02-15 (Phase 3)
