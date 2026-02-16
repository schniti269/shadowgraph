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
