from database import ShadowDB


def test_schema_creates_tables(tmp_db: ShadowDB):
    """Verify all tables and indexes are created."""
    cursor = tmp_db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    assert "anchors" in tables
    assert "edges" in tables
    assert "nodes" in tables


def test_upsert_and_get_node(tmp_db: ShadowDB):
    """Test inserting and retrieving a node."""
    tmp_db.upsert_node("test-1", "THOUGHT", "This is a test thought")
    node = tmp_db.get_node("test-1")
    assert node is not None
    assert node["type"] == "THOUGHT"
    assert node["content"] == "This is a test thought"


def test_upsert_node_replaces(tmp_db: ShadowDB):
    """Test that upserting the same ID replaces content."""
    tmp_db.upsert_node("test-1", "THOUGHT", "Original")
    tmp_db.upsert_node("test-1", "THOUGHT", "Updated")
    node = tmp_db.get_node("test-1")
    assert node["content"] == "Updated"


def test_upsert_anchor(tmp_db: ShadowDB):
    """Test inserting and retrieving anchors."""
    tmp_db.upsert_node("code:test.py:function:hello", "CODE_BLOCK", "def hello(): pass")
    tmp_db.upsert_anchor(
        "code:test.py:function:hello", "test.py", "function:hello", "abc123", 1
    )
    anchors = tmp_db.get_anchors_for_file("test.py")
    assert len(anchors) == 1
    assert anchors[0]["symbol_name"] == "function:hello"
    assert anchors[0]["status"] == "VALID"


def test_mark_stale(tmp_db: ShadowDB):
    """Test marking an anchor as stale."""
    tmp_db.upsert_node("code:test.py:function:hello", "CODE_BLOCK", "def hello(): pass")
    tmp_db.upsert_anchor(
        "code:test.py:function:hello", "test.py", "function:hello", "abc123", 1
    )
    tmp_db.mark_stale("code:test.py:function:hello", "test.py", "function:hello")

    stale = tmp_db.get_stale_anchors_for_file("test.py")
    assert len(stale) == 1
    assert stale[0]["status"] == "STALE"


def test_add_edge_and_get_thoughts(tmp_db: ShadowDB):
    """Test adding edges and retrieving thoughts for a symbol."""
    tmp_db.upsert_node("code:test.py:function:hello", "CODE_BLOCK", "def hello(): pass")
    tmp_db.upsert_anchor(
        "code:test.py:function:hello", "test.py", "function:hello", "abc123", 1
    )
    tmp_db.upsert_node("thought:001", "THOUGHT", "This function greets the world")
    tmp_db.add_edge("code:test.py:function:hello", "thought:001", "HAS_THOUGHT")

    thoughts = tmp_db.get_thoughts_for_symbol("test.py", "function:hello")
    assert len(thoughts) == 1
    assert thoughts[0]["content"] == "This function greets the world"


def test_get_thoughts_empty(tmp_db: ShadowDB):
    """Test that querying thoughts for nonexistent symbol returns empty."""
    thoughts = tmp_db.get_thoughts_for_symbol("nonexistent.py", "function:foo")
    assert thoughts == []


def test_get_node_nonexistent(tmp_db: ShadowDB):
    """Test that getting a nonexistent node returns None."""
    assert tmp_db.get_node("does-not-exist") is None
