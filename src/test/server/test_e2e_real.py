"""
TRUE END-TO-END TESTS — no mocking, no tmp_path, no tmp_db.

These tests import main.py exactly as the MCP server does, using the REAL
global `db` connected to .vscode/shadow.db, with cwd = project root.

They call the actual MCP tool functions and verify:
  1. Files exist on disk at the exact paths
  2. DB rows were actually written (raw sqlite3 queries)
  3. Return values are correct and consistent

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
# SETUP / TEARDOWN
# ============================================================================

def _clean_db_via_server():
    """Delete E2E test rows using the server's own db connection."""
    if "main" in sys.modules:
        conn = sys.modules["main"].db.conn
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("DELETE FROM edges WHERE source_id LIKE '%_e2e_test%' OR target_id LIKE '%_e2e_test%'")
            conn.execute("DELETE FROM anchors WHERE file_path LIKE '%_e2e_test%'")
            conn.execute("DELETE FROM nodes WHERE id LIKE '%_e2e_test%'")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
    else:
        os.makedirs(os.path.dirname(REAL_DB_PATH), exist_ok=True)
        if os.path.exists(REAL_DB_PATH):
            conn = sqlite3.connect(REAL_DB_PATH, timeout=10)
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.execute("DELETE FROM edges WHERE source_id LIKE '%_e2e_test%' OR target_id LIKE '%_e2e_test%'")
                conn.execute("DELETE FROM anchors WHERE file_path LIKE '%_e2e_test%'")
                conn.execute("DELETE FROM nodes WHERE id LIKE '%_e2e_test%'")
            except sqlite3.OperationalError:
                pass
            conn.commit()
            conn.close()


@pytest.fixture(autouse=True)
def clean_real_db_and_disk():
    scratch = TEST_SCRATCH_DIR
    _clean_db_via_server()
    shutil.rmtree(scratch, ignore_errors=True)
    yield
    _clean_db_via_server()
    shutil.rmtree(scratch, ignore_errors=True)


def raw_db():
    """Return a connection to the real shadow.db (reuses server's open connection)."""
    if "main" in sys.modules:
        conn = sys.modules["main"].db.conn
        conn.row_factory = sqlite3.Row
        return conn
    conn = sqlite3.connect(REAL_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def close_raw_db(conn):
    if "main" in sys.modules and conn is sys.modules["main"].db.conn:
        return
    conn.close()


def load_server():
    """Import main.py exactly as VS Code does when spawning the MCP server."""
    os.environ["SHADOW_DB_PATH"] = REAL_DB_PATH
    os.chdir(PROJECT_ROOT)
    import main as server
    return server


# ============================================================================
# TEST 1: create_file — file on disk + node in DB + verified_node not null
# ============================================================================

def test_e2e_create_file_disk_and_db():
    server = load_server()

    file_path = "_e2e_test_scratch/calc.py"
    content = "def add(a, b):\n    return a + b\n"

    result = json.loads(server.create_file(path=file_path, content=content, language="python"))
    print("\nresult:", json.dumps(result, indent=2))

    # File must exist on disk
    assert os.path.isfile(os.path.join(PROJECT_ROOT, file_path)), \
        f"File '{file_path}' NOT found on disk"

    # DB must have a CODE_BLOCK node
    conn = raw_db()
    nodes = conn.execute(
        "SELECT id, type FROM nodes WHERE id LIKE '%_e2e_test_scratch%calc%'"
    ).fetchall()
    close_raw_db(conn)
    assert len(nodes) > 0, "No CODE_BLOCK node in DB for created file"

    # verified_node must not be null
    assert result["verified_node"] is not None, \
        "verified_node is null — path normalisation failed"


# ============================================================================
# TEST 2: remember() with symbol link — must not raise FK error
# ============================================================================

def test_e2e_remember_links_to_symbol():
    """
    After indexing a file, remember() with file_path+symbol_name must succeed
    and store a THOUGHT linked to the CODE_BLOCK node.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/service.py"
    content = "def process(x):\n    return x\n"

    create_result = json.loads(server.create_file(path=file_path, content=content, language="python"))
    assert create_result["status"] == "ok"

    thought_result = json.loads(server.remember(
        topic="e2e-test-process",
        context="E2E test thought — must be stored in DB",
        file_path=file_path,
        symbol_name="function:process",
    ))
    print("remember:", json.dumps(thought_result, indent=2))

    assert thought_result["status"] == "ok", \
        f"remember() returned error: {thought_result.get('message', thought_result)}"
    assert thought_result["linked_to"] is not None
    assert not str(thought_result["linked_to"]).startswith("(unlinked"), \
        f"Symbol not found for linking: {thought_result['linked_to']}"

    # THOUGHT node must be in DB
    conn = raw_db()
    thought_id = thought_result["thought_id"]
    row = conn.execute("SELECT id, content FROM nodes WHERE id=?", (thought_id,)).fetchone()
    close_raw_db(conn)
    assert row is not None, f"THOUGHT node '{thought_id}' not found in DB"
    assert "E2E test thought" in row["content"]


# ============================================================================
# TEST 3: recall() — must return thoughts that were saved
# ============================================================================

def test_e2e_recall_returns_thoughts():
    """Full flow: create file → remember → recall must return the thought."""
    server = load_server()

    file_path = "_e2e_test_scratch/auth.py"
    content = "def login(user, password):\n    pass\n"

    server.create_file(path=file_path, content=content, language="python")
    server.remember(
        topic="e2e-login-security",
        context="Must validate against bcrypt hash — never plaintext",
        file_path=file_path,
        symbol_name="function:login",
    )

    # recall by symbol name
    result = json.loads(server.recall("function:login"))
    print("\nrecall:", json.dumps(result, indent=2))

    assert len(result["thoughts"]) > 0, \
        "recall() returned 0 thoughts after remember() — chain broken"
    assert any("bcrypt" in t["text"] for t in result["thoughts"]), \
        "Thought text not found in recall result"


# ============================================================================
# TEST 4: recall() with no args returns business context
# ============================================================================

def test_e2e_recall_empty_returns_business_context():
    """remember() with no file/symbol stores as business context, recall() returns it."""
    server = load_server()

    server.remember(
        topic="e2e-test-business-rule",
        context="E2E test business rule: always use DPD for shipping",
    )

    result = json.loads(server.recall())
    print("\nrecall():", json.dumps(result, indent=2))

    assert result["business_context"], "recall() returned no business context"
    assert any("DPD" in entry["text"] for entry in result["business_context"]), \
        "Business context not found in recall() result"


# ============================================================================
# TEST 5: index() path normalisation — no backslashes in node IDs
# ============================================================================

def test_e2e_index_path_separator_consistent():
    """On Windows, os.path.relpath returns backslashes. Node IDs must use forward slashes."""
    server = load_server()

    nested_path = "_e2e_test_scratch/nested/deep.py"
    content = "def deep_func():\n    pass\n"

    os.makedirs(os.path.join(PROJECT_ROOT, "_e2e_test_scratch", "nested"), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, nested_path), "w") as f:
        f.write(content)

    index_result = json.loads(server.index(
        file_path=os.path.join(PROJECT_ROOT, nested_path)
    ))
    print("\nindex:", json.dumps(index_result, indent=2))
    assert index_result["status"] == "ok"

    conn = raw_db()
    nodes = conn.execute(
        "SELECT id FROM nodes WHERE id LIKE '%_e2e_test_scratch%deep%'"
    ).fetchall()
    close_raw_db(conn)

    assert len(nodes) > 0, "No node stored after index()"
    for n in nodes:
        assert "\\" not in dict(n)["id"], \
            f"Node ID contains backslash: '{dict(n)['id']}' — path not normalised"


# ============================================================================
# TEST 6: Full workflow: create → index → remember → recall → check
# ============================================================================

def test_e2e_full_chain():
    """
    Full chain: create_file → remember → recall → check.
    All steps must succeed and data must be consistent end-to-end.
    """
    server = load_server()

    file_path = "_e2e_test_scratch/payments.py"
    content = (
        "def charge(amount, currency):\n"
        "    \"\"\"Charge a payment.\"\"\"\n"
        "    pass\n"
    )

    # Step 1: Create file
    create_res = json.loads(server.create_file(path=file_path, content=content, language="python"))
    print("\ncreate_file:", json.dumps(create_res, indent=2))
    assert create_res["status"] == "ok"
    assert os.path.isfile(os.path.join(PROJECT_ROOT, file_path))

    # Step 2: Remember why
    remember_res = json.loads(server.remember(
        topic="e2e-stripe-idempotency",
        context="Stripe idempotency key must be set — retry safe",
        file_path=file_path,
        symbol_name="function:charge",
    ))
    print("remember:", json.dumps(remember_res, indent=2))
    assert remember_res["status"] == "ok"
    assert remember_res["linked_to"] and not str(remember_res["linked_to"]).startswith("(unlinked")

    # Step 3: Recall
    recall_res = json.loads(server.recall("function:charge"))
    print("recall:", json.dumps(recall_res, indent=2))
    assert len(recall_res["thoughts"]) > 0, "recall() returned no thoughts"
    assert recall_res["symbols"], "recall() returned no code"
    assert any("Stripe" in t["text"] for t in recall_res["thoughts"])

    # Step 4: Raw DB check
    conn = raw_db()
    thought_id = remember_res["thought_id"]
    row = conn.execute("SELECT content FROM nodes WHERE id=?", (thought_id,)).fetchone()
    close_raw_db(conn)
    assert row is not None, "THOUGHT not in raw DB"
    assert "Stripe" in row["content"]

    # Step 5: Check (no stale since just created)
    check_res = json.loads(server.check(file_path=file_path))
    print("check:", json.dumps(check_res, indent=2))
    assert check_res["status"] == "ok"
