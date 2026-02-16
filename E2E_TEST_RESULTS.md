# E2E Test Results — All Tools Working

## Summary
Replaced fake unit tests with real end-to-end tests that call actual MCP tool functions against the real `.vscode/shadow.db` database. **All 6 E2E tests pass**, confirming all 5 critical bugs have been fixed.

## Real Bugs Found & Fixed

### Bug 1: Path Separator Mismatch (Windows backslash in DB)
**Problem:** `index_file()` used `os.path.relpath()` which returns backslash paths on Windows (e.g., `code:src\auth\login.py:function:authenticate`). Tools like `add_thought()` and `get_context()` passed user-provided forward-slash paths, causing node lookups to fail.

**Fixed by:** Normalizing all paths to forward slashes with `.replace("\\", "/")` in:
- `index_file()` — normalizes `relative_path`
- `create_file()` — normalizes path in node IDs
- `add_thought()` / `edit_code_with_thought()` — normalize user-provided paths

**Result:** DB stores consistent forward-slash paths. Node lookups succeed.

---

### Bug 2: `get_context()` Returns Empty Thoughts
**Problem:** `get_thoughts_for_symbol()` joins anchors by `file_path`. Anchors stored backslash paths, but queries passed forward-slash paths. Zero matches = zero thoughts.

**Fixed by:** Path normalization (Bug 1 fix). Now all paths are forward slashes, so joins succeed.

**Result:** `get_context()` now returns linked thoughts correctly.

---

### Bug 3: `create_folder()` Silently Fails (Directory Created, DB Node Not)
**Problem:** Existing `.vscode/shadow.db` was created with a CHECK constraint that didn't include `FOLDER` type: `CHECK(type IN ('CODE_BLOCK', 'THOUGHT', 'REQUIREMENT'))`. `CREATE TABLE IF NOT EXISTS` never updates existing tables, so `create_folder()` inserts failed with `CHECK constraint failed`.

**Fixed by:** Database migration in `_apply_migrations()`:
1. Detects existing tables with old CHECK constraint
2. Backs up all data
3. Drops and recreates the `nodes` table with updated constraint: `CHECK(type IN ('CODE_BLOCK', 'THOUGHT', 'REQUIREMENT', 'CONSTRAINT', 'FOLDER'))`
4. Restores backed-up data

**Result:** `create_folder()` inserts succeed. Both directory and DB node are created.

---

### Bug 4: `verified_node` Always Null in `create_file()`
**Problem:** Node ID had forward slashes (`code:src/auth.py:function:login`), but `verify_node()` looked it up in a DB that stored backslash IDs from previous auto-indexing. Query returned `null`.

**Fixed by:** Path normalization (Bug 1 fix). Now auto-indexed nodes match the normalized path used in verification.

**Result:** `verified_node` is returned correctly as proof of DB persistence.

---

### Bug 5: `add_thought()` Crashes with FK Error When Node Doesn't Exist
**Problem:** If a symbol wasn't indexed or had been indexed under a different path separator, `add_edge(code_node_id, thought_id, "HAS_THOUGHT")` would fail with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` because the source node didn't exist.

**Fixed by:** Wrapping `add_edge()` in try/catch to catch FK errors and return a proper error response instead of crashing:
```python
try:
    db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")
except Exception as e:
    if "FOREIGN KEY" in str(e):
        return json.dumps({
            "status": "error",
            "message": f"Code node not found: {code_node_id}. File must be indexed before adding thoughts."
        })
    raise
```

**Result:** Tools return clean error responses. Agents can handle missing symbols gracefully.

---

## E2E Test Suite

### Test 1: `test_e2e_create_file_disk_and_db`
✅ File exists on disk after creation
✅ CODE_BLOCK node created in DB
✅ `verified_node` is not null (proves persistence)

### Test 2: `test_e2e_add_thought_no_fk_error`
✅ `add_thought()` succeeds (no FK error)
✅ THOUGHT node persists in DB
✅ Edge links CODE_BLOCK → THOUGHT

### Test 3: `test_e2e_get_context_returns_thoughts`
✅ `get_context()` returns code content
✅ `get_context()` returns all linked thoughts
✅ Thought text is correct

### Test 4: `test_e2e_create_folder_db_node_exists`
✅ Directory created on disk
✅ FOLDER node created in DB (not rejected by CHECK constraint)
✅ `create_folder()` returns `status: "ok"`

### Test 5: `test_e2e_index_file_path_separator_consistent`
✅ Node IDs use forward slashes (not backslashes)
✅ Paths are normalized at storage time
✅ Downstream tools can find nodes consistently

### Test 6: `test_e2e_full_chain_create_index_thought_context`
✅ Full workflow: `create_file()` → auto-index → `add_thought()` → `get_context()`
✅ All steps succeed
✅ Data chain is consistent: file on disk, node in DB, thought linked, context retrievable

---

## Test Infrastructure

### Real DB Testing
- Tests use the **actual project DB** (`.vscode/shadow.db`), not temp `tmp_path` fixtures
- Tests call **real MCP tool functions** from `main.py`, not mocked versions
- All assertions verify **real filesystem and database state**, not mocked return values

### Connection Management
- Server's DB connection is reused to avoid "database is locked" errors
- Fixture cleans up test artifacts before and after each test
- Fresh schema created on first run, migrations tested on re-runs

### Assertions Prove Actual Execution
Every test verifies:
1. File exists on disk at exact expected path
2. DB row was written (raw `sqlite3` queries, not ORM)
3. Return values match actual state (not just success codes)

---

## Backward Compatibility

Old tests still pass (60 total):
- Database schema migrations preserve old data
- All existing APIs maintain compatibility
- New code normalizes paths internally; agents see same behavior

---

## Files Modified

- `src/server/main.py` — Path normalization + FK error handling
- `src/server/database.py` — Schema migration for FOLDER type
- `src/test/server/test_e2e_real.py` — Real E2E test suite (6 tests, all passing)

---

## Next Steps

1. **Monitor:** Track if any agents report path or FK issues in production
2. **Document:** Add to API docs that paths should use forward slashes
3. **Extend:** Add more E2E tests for edge cases (concurrent writes, very large files, unicode paths)
