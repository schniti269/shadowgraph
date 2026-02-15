from database import ShadowDB
from indexer import index_file
from drift import check_drift


def test_no_drift_when_unchanged(tmp_db: ShadowDB, sample_python_file: str):
    """Test that check_drift returns empty when code hasn't changed."""
    symbols = index_file(sample_python_file)
    for sym in symbols:
        node_id = f"code:test:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, sample_python_file, sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    stale = check_drift(tmp_db, sample_python_file)
    assert stale == []


def test_drift_detects_modification(tmp_db: ShadowDB, tmp_path):
    """Test that check_drift detects when a function body changes."""
    # Index original file
    f = tmp_path / "changing.py"
    f.write_text('def greet():\n    return "hello"\n')
    symbols = index_file(str(f))
    for sym in symbols:
        node_id = f"code:test:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, str(f), sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    # Modify the file
    f.write_text('def greet():\n    return "goodbye"\n')

    stale = check_drift(tmp_db, str(f))
    assert len(stale) == 1
    assert stale[0]["symbol_name"] == "function:greet"
    assert stale[0]["status"] == "MODIFIED"


def test_drift_detects_deletion(tmp_db: ShadowDB, tmp_path):
    """Test that check_drift detects when a function is deleted."""
    f = tmp_path / "deleting.py"
    f.write_text('def greet():\n    return "hello"\n\ndef farewell():\n    pass\n')
    symbols = index_file(str(f))
    for sym in symbols:
        node_id = f"code:test:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, str(f), sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    # Remove one function
    f.write_text('def greet():\n    return "hello"\n')

    stale = check_drift(tmp_db, str(f))
    assert len(stale) == 1
    assert stale[0]["symbol_name"] == "function:farewell"
    assert stale[0]["status"] == "DELETED"


def test_drift_marks_anchor_stale_in_db(tmp_db: ShadowDB, tmp_path):
    """Test that check_drift updates anchor status in the database."""
    f = tmp_path / "stale.py"
    f.write_text('def greet():\n    return "hello"\n')
    symbols = index_file(str(f))
    for sym in symbols:
        node_id = f"code:test:{sym['symbol_name']}"
        tmp_db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        tmp_db.upsert_anchor(
            node_id, str(f), sym["symbol_name"],
            sym["ast_hash"], sym["start_line"]
        )

    f.write_text('def greet():\n    return "changed"\n')
    check_drift(tmp_db, str(f))

    stale_anchors = tmp_db.get_stale_anchors_for_file(str(f))
    assert len(stale_anchors) == 1
    assert stale_anchors[0]["status"] == "STALE"
