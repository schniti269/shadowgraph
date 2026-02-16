# Debugging ShadowGraph

## F5 to Debug Extension

To debug the extension in VS Code, create `.vscode/launch.json` (not in git for security):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Extension (Debug)",
      "type": "extensionHost",
      "request": "launch",
      "args": [
        "--extensionDevelopmentPath=${workspaceFolder}"
      ],
      "outFiles": [
        "${workspaceFolder}/dist/**/*.js"
      ],
      "preLaunchTask": "npm: build"
    },
    {
      "name": "Python: Debug Server",
      "type": "python",
      "request": "launch",
      "module": "src.server.main",
      "console": "integratedTerminal",
      "justMyCode": true,
      "env": {
        "SHADOW_DB_PATH": "${workspaceFolder}/.vscode/shadow.db"
      },
      "cwd": "${workspaceFolder}"
    }
  ]
}
```

Then:
1. Press **F5** to start "Extension (Debug)"
2. A new VS Code window opens with the extension loaded
3. Breakpoints work in TypeScript (`.ts`) files in `src/client/`
4. Extension output appears in Debug Console

## Debug Python Server

In the same VS Code debug setup:
1. Select "Python: Debug Server" from Run menu
2. Click **Start Debugging** (F5)
3. Breakpoints work in `.py` files in `src/server/`
4. Server logs appear in Terminal

## Run Tests

### Unit Tests
```bash
npm run test:python
```

Runs 60 tests:
- 47 existing unit tests (isolated, tmp_path-based)
- 6 real E2E tests (against `.vscode/shadow.db`)
- 7 additional tests

### E2E Tests Only
```bash
pytest src/test/server/test_e2e_real.py -v
```

These tests:
- Call real MCP tool functions from `src/server/main.py`
- Use the actual `.vscode/shadow.db` database
- Verify files exist on disk
- Verify DB rows were written via raw sqlite3 queries

### Single Test
```bash
pytest src/test/server/test_e2e_real.py::test_e2e_create_file_disk_and_db -v
```

## Known Issues & Fixes

### Windows Path Separators
All paths stored in DB use **forward slashes (/)**, even on Windows. Tools normalize paths with:
```python
normalized_path = file_path.replace("\\", "/")
```

This ensures consistent lookups across all tools.

### Schema Migrations
Old databases (v0.3.6 and earlier) are automatically migrated on first connect:
- Adds `path` column if missing
- Fixes CHECK constraint to include FOLDER type
- Data is preserved during migration

### Database Locked Error
If tests fail with "database is locked":
1. Close all VS Code windows
2. Delete `.vscode/shadow.db` (tests create a fresh one)
3. Retry tests

## Logging

All logs are prefixed with `[ShadowGraph]` for easy filtering:

### Extension (TypeScript)
```
[ShadowGraph] Activating extension
[ShadowGraph] MCP server started
```

### MCP Server (Python)
```
[shadowgraph] === ShadowGraph MCP Server Starting ===
[shadowgraph] index_file() called with: src/auth.py
```

Filter in VS Code Output panel: `[ShadowGraph]`

## Key Files

- `src/server/main.py` — MCP tools (create_file, add_thought, get_context, etc.)
- `src/server/database.py` — SQLite schema + migrations
- `src/test/server/test_e2e_real.py` — Real E2E tests
- `.vscode/shadow.db` — Project database (gitignored)
- `E2E_TEST_RESULTS.md` — Detailed test findings and bug fixes
