"""
TRUE END-TO-END TESTS — no mocking, no tmp_path, no tmp_db.

These tests import main.py exactly as the MCP server does, using the REAL
global `db` connected to .vscode/shadow.db, with cwd = project root.

They call the actual MCP tool functions and verify:
  1. Files exist on disk at the exact paths
  2. DB rows were actually written (raw sqlite3 queries, not ORM)
  3. Return values are correct

Some of these tests are EXPECTED TO FAIL because they expose real bugs:
  - Path separator: Windows stores backslash, lookups use forward slash
  - Schema migration: FOLDER type rejected by old CHECK constraint
  - add_thought / get_context: FK fails because node ID mismatch

Run from project root:
    pytest src/test/server/test_e2e_real.py -v
"""

import json
import os
import sqlite3
import sys
import shutil

import pytest

# Add server directory to path BEFORE importing main
SERVER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "server")
sys.path.insert(0, os.path.abspath(SERVER_DIR))

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
REAL_DB_PATH = os.path.join(PROJECT_ROOT, ".vscode", "shadow.db")
TEST_SCRATCH_DIR = os.path.join(PROJECT_ROOT, "_e2e_test_scratch")


# ============================================================================
# SETUP / TEARDOWN: use the real DB, clean up test artifacts
# ============================================================================

def _clean_db_via_server():
    """
    Delete E2E test rows using the server's own db connection (already open).
    Must use the server module's db so we don't get 'database is locked'.
    """
    import sys
    if "main" in sys.modules:
        server = sys.modules["main"]
        conn = server.db.conn
        conn.execute("PRAGMA foreign_keys=OFF")
        # Only delete if tables exist (avoid errors on fresh DB)
        try:
            conn.execute("DELETE FROM edges WHERE source_id LIKE '%_e2e_test%' OR target_id LIKE '%_e2e_test%'")
            conn.execute("DELETE FROM anchors WHERE file_path LIKE '%_e2e_test%'")
            conn.execute("DELETE FROM nodes WHERE id LIKE '%_e2e_test%'")
        except sqlite3.OperationalError:
            pass  # Tables don't exist yet
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
    else:
        # Server not yet loaded — use a direct connection with timeout
        os.makedirs(os.path.dirname(REAL_DB_PATH), exist_ok=True)
        if os.path.exists(REAL_DB_PATH):
            conn = sqlite3.connect(REAL_DB_PATH, timeout=10)
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.execute("DELETE FROM edges WHERE source_id LIKE '%_e2e_test%' OR target_id LIKE '%_e2e_test%'")
                conn.execute("DELETE FROM anchors WHERE file_path LIKE '%_e2e_test%'")
                conn.execute("DELETE FROM nodes WHERE id LIKE '%_e2e_test%'")
            except sqlite3.OperationalError:
                pass  # Tables don't exist
            conn.commit()
            conn.close()


@pytest.fixture(autouse=True)
def clean_real_db_and_disk():
    """
    Before each test: delete any leftover nodes/anchors/edges from previous
    E2E runs. After each test: delete the scratch dir from disk.
    Uses the server's open connection to avoid 'database is locked'.
    """
    scratch = TEST_SCRATCH_DIR
    _clean_db_via_server()
    shutil.rmtree(scratch, ignore_errors=True)

    yield

    _clean_db_via_server()
    shutil.rmtree(scratch, ignore_errors=True)


def raw_db():
    """
    Return a connection to the real shadow.db.
    Re-uses the server's open connection if available (avoids WAL lock).
    """
    import sys
    if "main" in sys.modules:
        conn = sys.modules["main"].db.conn
        # Ensure row_factory is set
        conn.row_factory = sqlite3.Row
        return conn
    conn = sqlite3.connect(REAL_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def close_raw_db(conn):
    """Only close if it's NOT the server's shared connection."""
    import sys
    if "main" in sys.modules and conn is sys.modules["main"].db.conn:
        return  # Don't close the server's connection
    conn.close()


def load_server():
    """
    Import main.py so its globals (db, mcp) are initialized exactly as
    when VS Code starts the MCP server. Re-import is safe because Python
    caches modules — subsequent calls return the same module object.
    """
    import importlib
    os.environ["SHADOW_DB_PATH"] = REAL_DB_PATH
    # Must change cwd to project root — same as what VS Code does
    os.chdir(PROJECT_ROOT)
    import main as server
    return server


# ============================================================================
# TEST 1: create_file — file must exist on disk AND node in DB
# ============================================================================

def test_e2e_create_file_disk_and_db():
    """
    create_file() must:
    1. Write the file to disk
    2. Create a CODE_BLOCK node in the real DB
    3. Return verified_node (not null)

    KNOWN BUG: verified_node is null on Windows because the node is stored
    with backslash paths but verify_node() looks up with forward slash.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/calc.py"
    content = "def add(a, b):\n    return a + b\n"

    result = json.loads(server.create_file(
        path=file_path,
        content=content,
        language="python",
    ))

    print("\nresult:", json.dumps(result, indent=2))

    # 1. File must exist on disk
    assert os.path.isfile(os.path.join(PROJECT_ROOT, file_path)), \
        f"File '{file_path}' NOT found on disk"

    # 2. DB must have a CODE_BLOCK node for this file
    conn = raw_db()
    nodes = conn.execute(
        "SELECT id, type FROM nodes WHERE id LIKE '%_e2e_test_scratch/calc%' "
        "OR id LIKE '%_e2e_test_scratch\\calc%'"
    ).fetchall()
    close_raw_db(conn)

    assert len(nodes) > 0, \
        f"No CODE_BLOCK node in DB for '{file_path}' — DB write failed"

    # 3. verified_node must not be null (this is the bug: it IS null on Windows)
    assert result["verified_node"] is not None, \
        "BUG: verified_node is null — path separator mismatch (backslash vs forward slash)"


# ============================================================================
# TEST 2: add_thought — must NOT raise FK error
# ============================================================================

def test_e2e_add_thought_no_fk_error():
    """
    After indexing a file, add_thought() must succeed — not raise
    FOREIGN KEY constraint failed.

    KNOWN BUG: On Windows, index_file stores node IDs with backslash separators
    (e.g. 'code:_e2e_test_scratch\\calc.py:function:add') but add_thought builds
    the lookup ID with forward slash ('code:_e2e_test_scratch/calc.py:function:add').
    The source node doesn't exist, so the FK edge insert fails.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/service.py"
    content = "def process(x):\n    return x\n"

    # Create and auto-index the file
    create_result = json.loads(server.create_file(
        path=file_path,
        content=content,
        language="python",
    ))
    print("\ncreate_file:", json.dumps(create_result, indent=2))
    assert create_result["status"] == "ok"

    # Now add a thought — this is what agents do
    try:
        thought_result = json.loads(server.add_thought(
            file_path=file_path,
            symbol_name="function:process",
            thought_text="E2E test thought — must be stored in DB",
        ))
    except Exception as exc:
        pytest.fail(
            f"BUG: add_thought raised {type(exc).__name__}: {exc}\n"
            f"Root cause: node ID in DB uses backslash but add_thought builds forward-slash key"
        )
    print("add_thought:", json.dumps(thought_result, indent=2))

    assert thought_result["status"] == "ok", \
        f"BUG: add_thought returned error: {thought_result.get('message', thought_result)}"

    # Verify THOUGHT node is in DB
    conn = raw_db()
    thought_id = thought_result["thought_id"]
    row = conn.execute("SELECT id, content FROM nodes WHERE id=?", (thought_id,)).fetchone()
    close_raw_db(conn)

    assert row is not None, \
        f"THOUGHT node '{thought_id}' not found in real DB — write was lost"
    assert "E2E test thought" in row["content"]


# ============================================================================
# TEST 3: get_context — must return thoughts that were added
# ============================================================================

def test_e2e_get_context_returns_thoughts():
    """
    Full flow: create file → add thought → get_context must return that thought.

    KNOWN BUG: get_context returns empty thoughts array even after add_thought
    succeeds, because get_thoughts_for_symbol() joins anchors by file_path,
    but anchors store backslash paths while the query uses forward slash.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/auth.py"
    content = "def login(user, password):\n    pass\n"

    server.create_file(path=file_path, content=content, language="python")
    try:
        server.add_thought(
            file_path=file_path,
            symbol_name="function:login",
            thought_text="Must validate against bcrypt hash — never plaintext",
        )
    except Exception as exc:
        pytest.fail(f"BUG: add_thought raised {type(exc).__name__}: {exc}")

    context = json.loads(server.get_context(
        file_path=file_path,
        symbol_name="function:login",
    ))
    print("\nget_context:", json.dumps(context, indent=2))

    assert len(context["thoughts"]) > 0, \
        "BUG: get_context returned 0 thoughts after add_thought — path mismatch in anchor lookup"
    assert any("bcrypt" in t["text"] for t in context["thoughts"]), \
        "BUG: thought text not found in context"


# ============================================================================
# TEST 4: create_folder — DB node must be created (not just the directory)
# ============================================================================

def test_e2e_create_folder_db_node_exists():
    """
    create_folder() must create a FOLDER node in the DB.

    KNOWN BUG: existing databases were created without FOLDER in the CHECK
    constraint. CREATE TABLE IF NOT EXISTS does NOT update existing tables,
    so FOLDER inserts fail with CHECK constraint error on old DBs.
    """
    server = load_server()

    folder_path = "_e2e_test_scratch/models"

    result = json.loads(server.create_folder(
        path=folder_path,
        name="models",
        description="E2E test folder",
    ))
    print("\ncreate_folder:", json.dumps(result, indent=2))

    # Directory must exist on disk
    assert os.path.isdir(os.path.join(PROJECT_ROOT, folder_path)), \
        f"Directory '{folder_path}' not created on disk"

    # FOLDER node must be in DB
    assert result["status"] == "ok", \
        f"BUG: create_folder status is '{result['status']}': {result.get('message', '')}"

    conn = raw_db()
    folder_node = conn.execute(
        "SELECT id, type FROM nodes WHERE type='FOLDER' AND id LIKE '%_e2e_test_scratch%'"
    ).fetchone()
    close_raw_db(conn)

    assert folder_node is not None, \
        "BUG: FOLDER node not in DB — CHECK constraint rejected 'FOLDER' type (schema migration missing)"


# ============================================================================
# TEST 5: index_file path normalization on Windows
# ============================================================================

def test_e2e_index_file_path_separator_consistent():
    """
    On Windows, os.path.relpath returns backslashes.
    Node IDs and anchor file_paths must use consistent separators so that
    downstream tools (add_thought, get_context) can find nodes by path.

    KNOWN BUG: index_file stores 'code:foo\\bar.py:function:x' but
    add_thought looks up 'code:foo/bar.py:function:x' — mismatch.
    """
    server = load_server()

    # Create a nested file (path has separator)
    nested_path = "_e2e_test_scratch/nested/deep.py"
    content = "def deep_func():\n    pass\n"

    os.makedirs(os.path.join(PROJECT_ROOT, "_e2e_test_scratch", "nested"), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, nested_path), "w") as f:
        f.write(content)

    index_result = json.loads(server.index_file(
        file_path=os.path.join(PROJECT_ROOT, nested_path)
    ))
    print("\nindex_file:", json.dumps(index_result, indent=2))
    assert index_result["status"] == "ok"

    # Check what path separator was stored in DB
    conn = raw_db()
    nodes = conn.execute(
        "SELECT id FROM nodes WHERE id LIKE '%_e2e_test_scratch%deep%'"
    ).fetchall()
    close_raw_db(conn)

    print("Stored node IDs:", [n["id"] for n in nodes])
    assert len(nodes) > 0, "No node stored after index_file"

    stored_id = nodes[0]["id"]

    # The stored ID must use forward slashes so add_thought can find it
    assert "\\" not in stored_id, \
        f"BUG: node ID contains backslash: '{stored_id}' — " \
        f"Windows path not normalized. add_thought will fail with FK error."


# ============================================================================
# TEST 6: Full workflow proves all tools chain correctly
# ============================================================================

def test_e2e_full_chain_create_index_thought_context():
    """
    Full chain: create_file → (auto-indexes) → add_thought → get_context.
    All three steps must succeed and the data must be consistent end-to-end.

    This test will FAIL if ANY of the above bugs exist.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/payments.py"
    content = (
        "def charge(amount, currency):\n"
        "    \"\"\"Charge a payment.\"\"\"\n"
        "    pass\n"
    )

    # Step 1: Create file
    create_res = json.loads(server.create_file(
        path=file_path,
        content=content,
        language="python",
    ))
    print("\ncreate_file:", json.dumps(create_res, indent=2))
    assert create_res["status"] == "ok", f"create_file failed: {create_res}"
    assert os.path.isfile(os.path.join(PROJECT_ROOT, file_path)), "File not on disk"

    # Step 2: Add thought
    try:
        thought_res = json.loads(server.add_thought(
            file_path=file_path,
            symbol_name="function:charge",
            thought_text="Stripe idempotency key must be set — retry safe",
        ))
    except Exception as exc:
        pytest.fail(f"BUG: add_thought raised {type(exc).__name__}: {exc}")
    print("add_thought:", json.dumps(thought_res, indent=2))
    assert thought_res["status"] == "ok", \
        f"BUG: add_thought returned error (likely FK/path mismatch): {thought_res}"

    # Step 3: Get context
    ctx = json.loads(server.get_context(
        file_path=file_path,
        symbol_name="function:charge",
    ))
    print("get_context:", json.dumps(ctx, indent=2))

    assert len(ctx["thoughts"]) > 0, \
        "BUG: get_context returned no thoughts — chain broken"
    assert ctx["code"] is not None, \
        "BUG: get_context returned no code — node lookup failed"
    assert any("Stripe" in t["text"] for t in ctx["thoughts"]), \
        "Thought text not found in context"

    # Step 4: Raw DB check — thought must be in DB
    conn = raw_db()
    thought_id = thought_res["thought_id"]
    row = conn.execute("SELECT content FROM nodes WHERE id=?", (thought_id,)).fetchone()
    close_raw_db(conn)
    assert row is not None, "THOUGHT not in raw DB"
    assert "Stripe" in row["content"]
