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
