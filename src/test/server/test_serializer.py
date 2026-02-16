"""Tests for serializer and deserializer modules."""

import json
import os
import tempfile
import pytest

from database import ShadowDB
from serializer import serialize_database, get_database_checksum
from deserializer import deserialize_database, detect_jsonl_conflicts


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = ShadowDB(db_path)
        db.connect()
        yield db, tmpdir
        db.close()


def test_serialize_empty_database(temp_db):
    """Serializing an empty database produces valid JSONL with no items."""
    db, tmpdir = temp_db
    output = os.path.join(tmpdir, "graph.jsonl")

    serialize_database(db.db_path, output)

    assert os.path.exists(output)
    with open(output) as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 0


def test_serialize_with_nodes(temp_db):
    """Serialize database with nodes produces one line per node."""
    db, tmpdir = temp_db

    # Add some nodes
    db.upsert_node("node1", "CODE_BLOCK", "def foo(): pass")
    db.upsert_node("node2", "THOUGHT", "Important observation")

    output = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, output)

    with open(output) as f:
        lines = [line.strip() for line in f if line.strip()]

    # Should have at least 2 nodes
    node_lines = [json.loads(line) for line in lines if json.loads(line)["type"] == "node"]
    assert len(node_lines) >= 2

    # Check node content
    node_ids = [n["id"] for n in node_lines]
    assert "node1" in node_ids
    assert "node2" in node_ids


def test_serialize_with_anchors(temp_db):
    """Serialize includes anchors with all fields."""
    db, tmpdir = temp_db

    db.upsert_node("node1", "CODE_BLOCK", "def login(): pass")
    db.upsert_anchor("node1", "auth.py", "function:login", "hash123", 42)

    output = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, output)

    with open(output) as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    anchor_lines = [line for line in lines if line["type"] == "anchor"]
    assert len(anchor_lines) == 1
    assert anchor_lines[0]["symbol_name"] == "function:login"
    assert anchor_lines[0]["file_path"] == "auth.py"
    assert anchor_lines[0]["status"] == "VALID"


def test_serialize_with_edges(temp_db):
    """Serialize includes edges with relationships."""
    db, tmpdir = temp_db

    db.upsert_node("code1", "CODE_BLOCK", "def charge(): pass")
    db.upsert_node("thought1", "THOUGHT", "Idempotent payment")
    db.add_edge("code1", "thought1", "HAS_THOUGHT")

    output = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, output)

    with open(output) as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    edge_lines = [line for line in lines if line["type"] == "edge"]
    assert len(edge_lines) == 1
    assert edge_lines[0]["relation"] == "HAS_THOUGHT"


def test_deserialize_creates_nodes(temp_db):
    """Deserialize JSONL creates nodes in database."""
    db, tmpdir = temp_db
    db.close()  # Close first DB

    # Create JSONL manually
    jsonl_path = os.path.join(tmpdir, "graph.jsonl")
    with open(jsonl_path, 'w') as f:
        f.write(json.dumps({"type": "node", "id": "node1", "node_type": "CODE_BLOCK", "content": "def foo(): pass", "created_at": "2026-02-16T10:00:00"}) + "\n")
        f.write(json.dumps({"type": "node", "id": "node2", "node_type": "THOUGHT", "content": "A note", "created_at": "2026-02-16T10:05:00"}) + "\n")

    # Load into fresh DB
    db_path = os.path.join(tmpdir, "test2.db")
    db2 = ShadowDB(db_path)
    db2.connect()
    deserialize_database(jsonl_path, db_path, merge_mode=False)

    # Verify
    node1 = db2.get_node("node1")
    assert node1 is not None
    assert node1["type"] == "CODE_BLOCK"

    node2 = db2.get_node("node2")
    assert node2 is not None
    assert node2["type"] == "THOUGHT"

    db2.close()


def test_deserialize_creates_anchors(temp_db):
    """Deserialize JSONL creates anchors in database."""
    db, tmpdir = temp_db
    db.close()

    jsonl_path = os.path.join(tmpdir, "graph.jsonl")
    with open(jsonl_path, 'w') as f:
        f.write(json.dumps({"type": "node", "id": "code1", "node_type": "CODE_BLOCK", "content": "code", "created_at": "2026-02-16T10:00:00"}) + "\n")
        f.write(json.dumps({"type": "anchor", "node_id": "code1", "file_path": "test.py", "symbol_name": "function:foo", "ast_hash": "hash1", "start_line": 10, "status": "VALID"}) + "\n")

    db_path = os.path.join(tmpdir, "test2.db")
    db2 = ShadowDB(db_path)
    db2.connect()
    deserialize_database(jsonl_path, db_path, merge_mode=False)

    anchors = db2.get_anchors_for_file("test.py")
    assert len(anchors) == 1
    assert anchors[0]["symbol_name"] == "function:foo"

    db2.close()


def test_round_trip_serialization(temp_db):
    """Serialize then deserialize preserves all data."""
    db, tmpdir = temp_db

    # Add diverse data
    db.upsert_node("code:app.py:login", "CODE_BLOCK", "def login(): pass")
    db.upsert_node("thought:abc123", "THOUGHT", "Security critical")
    db.upsert_anchor("code:app.py:login", "app.py", "function:login", "hash456", 15)
    db.add_edge("code:app.py:login", "thought:abc123", "HAS_THOUGHT")

    # Serialize
    serialize_path = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, serialize_path)

    # Clear original DB
    db.conn.execute("DELETE FROM edges")
    db.conn.execute("DELETE FROM anchors")
    db.conn.execute("DELETE FROM nodes")
    db.conn.commit()

    # Deserialize into same DB
    deserialize_database(serialize_path, db.db_path, merge_mode=False)

    # Verify round-trip
    assert db.get_node("code:app.py:login") is not None
    assert db.get_node("thought:abc123") is not None
    anchors = db.get_anchors_for_file("app.py")
    assert len(anchors) == 1

    db.close()


def test_merge_mode_prefers_newer(temp_db):
    """In merge mode, newer created_at wins."""
    db, tmpdir = temp_db

    # Add initial node with old timestamp
    db.upsert_node("node1", "CODE_BLOCK", "old content")
    db.conn.execute(
        "UPDATE nodes SET created_at = '2026-02-16T10:00:00' WHERE id = 'node1'"
    )
    db.conn.commit()

    # Serialize
    serialize_path = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, serialize_path)

    # Modify JSONL to have newer content
    with open(serialize_path, 'r') as f:
        lines = f.readlines()

    with open(serialize_path, 'w') as f:
        for line in lines:
            item = json.loads(line)
            if item.get("id") == "node1":
                item["content"] = "new content"
                item["created_at"] = "2026-02-16T11:00:00"
            f.write(json.dumps(item) + "\n")

    # Deserialize in merge mode
    deserialize_database(serialize_path, db.db_path, merge_mode=True)

    # Should have new content
    node = db.get_node("node1")
    assert node["content"] == "new content"

    db.close()


def test_stale_merge_strategy(temp_db):
    """In merge mode, STALE status is sticky (stale-once-stale-always)."""
    db, tmpdir = temp_db

    db.upsert_node("code1", "CODE_BLOCK", "code")
    db.upsert_anchor("code1", "app.py", "func", "hash1", 10)
    db.mark_stale("code1", "app.py", "func")

    # Serialize with STALE status
    serialize_path = os.path.join(tmpdir, "graph.jsonl")
    serialize_database(db.db_path, serialize_path)

    # Clear and deserialize with merge=True
    db.conn.execute("DELETE FROM edges")
    db.conn.execute("DELETE FROM anchors")
    db.conn.execute("DELETE FROM nodes")
    db.conn.commit()

    deserialize_database(serialize_path, db.db_path, merge_mode=True)

    # Should still be STALE
    anchors = db.get_anchors_for_file("app.py")
    assert anchors[0]["status"] == "STALE"

    db.close()


def test_detect_jsonl_conflicts():
    """detect_jsonl_conflicts finds items with duplicate IDs but different content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = os.path.join(tmpdir, "graph.jsonl")

        # Create JSONL with conflict: same node ID, different content
        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "node", "id": "node1", "node_type": "CODE_BLOCK", "content": "version1", "created_at": "2026-02-16T10:00:00"}) + "\n")
            f.write(json.dumps({"type": "node", "id": "node1", "node_type": "CODE_BLOCK", "content": "version2", "created_at": "2026-02-16T10:05:00"}) + "\n")

        conflicts = detect_jsonl_conflicts(jsonl_path)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "node"


def test_get_database_checksum(temp_db):
    """get_database_checksum produces consistent hash."""
    db, tmpdir = temp_db

    db.upsert_node("node1", "CODE_BLOCK", "content")
    checksum1 = get_database_checksum(db.db_path)

    # Same content should produce same checksum
    checksum2 = get_database_checksum(db.db_path)
    assert checksum1 == checksum2

    # Add node, checksum changes
    db.upsert_node("node2", "THOUGHT", "thought")
    checksum3 = get_database_checksum(db.db_path)
    assert checksum3 != checksum1

    db.close()


def test_empty_jsonl_deserializes(temp_db):
    """Deserialize empty JSONL doesn't error."""
    db, tmpdir = temp_db
    db.close()

    jsonl_path = os.path.join(tmpdir, "empty.jsonl")
    with open(jsonl_path, 'w') as f:
        f.write("")  # Empty file

    db_path = os.path.join(tmpdir, "test2.db")
    db2 = ShadowDB(db_path)
    db2.connect()

    # Should not raise
    deserialize_database(jsonl_path, db_path, merge_mode=False)

    db2.close()
