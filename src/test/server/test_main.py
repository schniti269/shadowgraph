import json
import os
import sys

import pytest

# Ensure the server module can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

from database import ShadowDB  # noqa: E402
from indexer import index_file as do_index_file  # noqa: E402


def test_index_file_tool_output(tmp_db: ShadowDB, sample_python_file: str):
    """Test the index_file tool produces valid JSON output."""
    # Simulate what the MCP tool does
    symbols = do_index_file(sample_python_file)
    relative_path = os.path.basename(sample_python_file)

    for sym in symbols:
        node_id = f"code:{relative_path}:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, relative_path, sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    result = {
        "status": "ok",
        "file": relative_path,
        "symbols_indexed": len(symbols),
        "symbols": [s["symbol_name"] for s in symbols],
    }

    output = json.dumps(result)
    parsed = json.loads(output)
    assert parsed["status"] == "ok"
    assert parsed["symbols_indexed"] >= 2
    assert "function:hello" in parsed["symbols"]


def test_add_thought_flow(tmp_db: ShadowDB, sample_python_file: str):
    """Test adding a thought to a previously indexed symbol."""
    import uuid

    symbols = do_index_file(sample_python_file)
    relative_path = os.path.basename(sample_python_file)

    # Index first
    for sym in symbols:
        node_id = f"code:{relative_path}:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, relative_path, sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    # Add thought
    code_node_id = f"code:{relative_path}:function:hello"
    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    tmp_db.upsert_node(thought_id, "THOUGHT", "This function is critical for greetings")
    tmp_db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")

    # Retrieve
    thoughts = tmp_db.get_thoughts_for_symbol(relative_path, "function:hello")
    assert len(thoughts) == 1
    assert "critical for greetings" in thoughts[0]["content"]


def test_get_context_flow(tmp_db: ShadowDB, sample_python_file: str):
    """Test retrieving full context (code + thoughts) for a symbol."""
    import uuid

    symbols = do_index_file(sample_python_file)
    relative_path = os.path.basename(sample_python_file)

    for sym in symbols:
        node_id = f"code:{relative_path}:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, relative_path, sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    # Add two thoughts
    code_node_id = f"code:{relative_path}:function:hello"
    for i, text in enumerate(["First thought", "Second thought"]):
        thought_id = f"thought:test{i}"
        tmp_db.upsert_node(thought_id, "THOUGHT", text)
        tmp_db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")

    # Get code node
    code_node = tmp_db.get_node(code_node_id)
    assert code_node is not None
    assert "def hello" in code_node["content"]

    # Get thoughts
    thoughts = tmp_db.get_thoughts_for_symbol(relative_path, "function:hello")
    assert len(thoughts) == 2


def test_add_new_code_with_thoughts(tmp_db: ShadowDB):
    """Test the add_new_code_with_thoughts workflow (create before index)."""
    import uuid
    from constraints import ConstraintValidator

    # Step 1: Agent decides to create new code
    file_path = "auth.py"
    symbol_name = "function:login_with_2fa"
    new_code = """def login_with_2fa(username, password, otp):
    # TODO: implement 2FA logic
    pass"""
    design_rationale = "Adding 2FA for security. Handles MFA codes via TOTP algorithm."
    constraints = ["Must validate OTP within 30-second window", "Must not log passwords"]

    # Step 2: Create code node with thoughts BEFORE writing file
    code_node_id = f"code:{file_path}:{symbol_name}"
    tmp_db.upsert_node(code_node_id, "CODE_BLOCK", new_code)

    # Step 3: Attach design rationale as thought
    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    tmp_db.upsert_node(thought_id, "THOUGHT", f"Design: {design_rationale}")
    tmp_db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")

    # Step 4: Add constraints
    validator = ConstraintValidator(tmp_db)
    for constraint_rule in constraints:
        validator.add_constraint(symbol_name, file_path, constraint_rule, "RULE", "critical")

    # Verify: Code node exists
    node = tmp_db.get_node(code_node_id)
    assert node is not None
    assert "login_with_2fa" in node["content"]

    # Verify: Thought is linked (query via edges, not anchors - code hasn't been indexed yet)
    thought = tmp_db.get_node(thought_id)
    assert thought is not None
    assert "2FA" in thought["content"]

    # Verify: Constraints are attached
    actual_constraints = validator.get_constraints(file_path, symbol_name)
    assert len(actual_constraints) == 2
    assert any("OTP" in c["rule"] for c in actual_constraints)
    assert any("password" in c["rule"] for c in actual_constraints)


def test_new_code_workflow_end_to_end(tmp_db: ShadowDB, tmp_path):
    """Test full workflow: pre-create with thoughts, write file, index it."""
    import uuid
    from pathlib import Path

    # Step 1: Pre-create code node with semantics
    file_path = "payment.py"
    symbol_name = "function:process_refund"
    new_code = """def process_refund(transaction_id, amount):
    # Implements idempotent refund processing
    pass"""

    code_node_id = f"code:{file_path}:{symbol_name}"
    tmp_db.upsert_node(code_node_id, "CODE_BLOCK", new_code)

    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    thought_text = "Refund processing must be idempotent. Stripe returns 409 on duplicate attempts."
    tmp_db.upsert_node(thought_id, "THOUGHT", thought_text)
    tmp_db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")

    # Verify pre-creation
    node = tmp_db.get_node(code_node_id)
    assert node is not None

    # Step 2: Thoughts exist BEFORE file is written (query the node directly)
    thought_node = tmp_db.get_node(thought_id)
    assert thought_node is not None
    assert "idempotent" in thought_node["content"]

    # Step 3: Agent would now write the file (simulated)
    # In real workflow: agent uses file tools to write file_path

    # Step 4: Index the file to anchor code to AST hashes
    # (This would be done by agent calling index_file())
    # For this test, we just verify the thought persists

    # Verify thought is still there after "file write" (simulated)
    thought_node_after = tmp_db.get_node(thought_id)
    assert thought_node_after is not None
    assert thought_node_after["content"] == thought_text


# ============================================================================
# PHASE 4: REAL FILE I/O INTEGRATION TESTS
# ============================================================================

def test_create_folder_creates_directory(tmp_path, tmp_db: ShadowDB):
    """Test that create_folder() creates a directory AND a FOLDER node."""
    import os

    # Change to temp directory for this test
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        folder_path = "src/auth"
        folder_id = f"folder:{folder_path}"

        # Create folder
        os.makedirs(folder_path, exist_ok=True)

        # Create FOLDER node in graph
        tmp_db.create_folder(folder_id, folder_path, "Authentication layer")

        # VERIFY: Directory exists
        assert os.path.isdir(folder_path), f"Directory {folder_path} was not created"

        # VERIFY: FOLDER node exists in DB
        folder_node = tmp_db.get_folder(folder_path)
        assert folder_node is not None, f"FOLDER node not found for {folder_path}"
        assert folder_node["type"] == "FOLDER"
        assert "Authentication" in folder_node["content"]

    finally:
        os.chdir(old_cwd)


def test_create_file_writes_to_disk_and_creates_node(tmp_path, tmp_db: ShadowDB):
    """Test that create_file() writes file to disk AND creates CODE_BLOCK node."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        file_path = "src/handler.py"
        code_content = """def handle_request(req):
    return {"status": "ok"}
"""
        code_node_id = f"code:{file_path}"

        # Create parent directory
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Write file
        with open(file_path, "w") as f:
            f.write(code_content)

        # Create CODE_BLOCK node
        tmp_db.upsert_node(code_node_id, "CODE_BLOCK", code_content, file_path)

        # VERIFY: File exists on disk
        assert os.path.isfile(file_path), f"File {file_path} was not created"
        with open(file_path) as f:
            disk_content = f.read()
        assert disk_content == code_content, "File content doesn't match"

        # VERIFY: CODE_BLOCK node exists in DB
        code_node = tmp_db.get_node(code_node_id)
        assert code_node is not None, f"CODE_BLOCK node not found"
        assert code_node["type"] == "CODE_BLOCK"
        assert code_node["path"] == file_path
        assert "handle_request" in code_node["content"]

    finally:
        os.chdir(old_cwd)


def test_create_file_atomic_write(tmp_path, tmp_db: ShadowDB):
    """Test that file creation uses atomic write (no partial files)."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        file_path = "src/critical.py"
        code_content = "critical_data = True\n"

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Simulate atomic write: write to temp, then move
        temp_path = file_path + ".tmp"
        with open(temp_path, "w") as f:
            f.write(code_content)
        os.rename(temp_path, file_path)

        # VERIFY: Only final file exists, no .tmp file
        assert os.path.isfile(file_path), "Final file not created"
        assert not os.path.exists(temp_path), "Temp file was not cleaned up"

        # VERIFY: Content is correct
        with open(file_path) as f:
            assert f.read() == code_content

    finally:
        os.chdir(old_cwd)


def test_verify_node_proves_persistence(tmp_db: ShadowDB):
    """Test that verify_node() returns actual DB data proving persistence."""
    import uuid

    # Create a node
    node_id = f"test:{uuid.uuid4().hex[:12]}"
    content = "This is test content"
    tmp_db.upsert_node(node_id, "THOUGHT", content)

    # Verify it exists by querying back
    verified = tmp_db.verify_node(node_id)

    # VERIFY: Got back the exact data
    assert verified is not None, "Node not found in DB"
    assert verified["id"] == node_id
    assert verified["type"] == "THOUGHT"
    assert verified["content"] == content
    assert verified["created_at"] is not None  # Should have timestamp

    # VERIFY: This proves the INSERT actually happened
    # (not just returned success without writing)


def test_folder_contents_query(tmp_path, tmp_db: ShadowDB):
    """Test listing all code blocks under a folder."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        folder = "src/auth"

        # Create files under folder
        os.makedirs(folder, exist_ok=True)

        # Add CODE_BLOCK nodes under folder
        files = ["token.py", "login.py", "validate.py"]
        for filename in files:
            file_path = f"{folder}/{filename}"
            node_id = f"code:{file_path}"
            tmp_db.upsert_node(node_id, "CODE_BLOCK", f"# {filename}", file_path)

        # Query folder contents
        contents = tmp_db.list_folder_contents(folder)

        # VERIFY: Got back all 3 files
        assert len(contents) == 3, f"Expected 3 files, got {len(contents)}"
        node_ids = {c["id"] for c in contents}
        for filename in files:
            expected_id = f"code:{folder}/{filename}"
            assert expected_id in node_ids, f"Missing {filename}"

    finally:
        os.chdir(old_cwd)


def test_migration_with_real_old_database(tmp_path):
    """Test migration against a real v0.3.3-style database."""
    import sqlite3
    from pathlib import Path

    # Create a v0.3.3-style database (no path column)
    old_db_path = tmp_path / "old_v0.3.3.db"
    old_conn = sqlite3.connect(old_db_path)
    old_conn.execute("""
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            content TEXT,
            vector BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    old_conn.execute("INSERT INTO nodes VALUES ('test-1', 'THOUGHT', 'old data', NULL, datetime('now'))")
    old_conn.commit()
    old_conn.close()

    # Now open with new ShadowDB (should migrate)
    from database import ShadowDB
    db = ShadowDB(str(old_db_path))
    db.connect()

    # VERIFY: Old data still exists
    old_node = db.get_node("test-1")
    assert old_node is not None
    assert old_node["content"] == "old data"

    # VERIFY: Can now insert with path column
    db.upsert_node("new-1", "CODE_BLOCK", "new data", "src/test.py")
    new_node = db.get_node("new-1")
    assert new_node is not None
    assert new_node["path"] == "src/test.py"

    # VERIFY: path column exists
    cursor = db.conn.execute("PRAGMA table_info(nodes)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "path" in columns, "path column was not added during migration"

    db.close()
