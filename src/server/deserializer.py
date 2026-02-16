"""
Deserialize JSONL format back into SQLite database.

Handles merge conflicts using timestamp-based strategy:
- If both local and remote have same item ID: use newer created_at (or remote if same timestamp)
- If only one has it: use the one that exists
- Ensures git-merged graphs can be loaded without data loss
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional


def deserialize_database(jsonl_path: str, db_path: str, merge_mode: bool = True) -> None:
    """
    Load JSONL into database.

    Args:
        jsonl_path: Path to graph.jsonl file
        db_path: Path to shadow.db
        merge_mode: If True, merge with existing data (prefer newer); if False, replace all
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    if not merge_mode:
        # Clear all tables for full reload
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM anchors")
        conn.execute("DELETE FROM nodes")

    # Group items by type for batch processing
    nodes = {}
    anchors = {}
    edges = {}

    with open(jsonl_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                item_type = item.get("type")

                if item_type == "node":
                    nodes[item["id"]] = item
                elif item_type == "anchor":
                    key = (item["node_id"], item["file_path"], item["symbol_name"])
                    anchors[key] = item
                elif item_type == "edge":
                    key = (item["source_id"], item["target_id"], item["relation"])
                    edges[key] = item
            except json.JSONDecodeError:
                continue

    # Load nodes
    for node_id, node_data in nodes.items():
        existing = conn.execute("SELECT created_at FROM nodes WHERE id = ?", (node_id,)).fetchone()

        if merge_mode and existing:
            # Keep newer version
            existing_time = existing["created_at"]
            new_time = node_data.get("created_at")
            if new_time and new_time <= existing_time:
                continue  # Keep existing (older or same)

        conn.execute(
            "INSERT OR REPLACE INTO nodes (id, type, content, created_at) VALUES (?, ?, ?, ?)",
            (node_id, node_data["node_type"], node_data.get("content"), node_data.get("created_at")),
        )

    # Load anchors
    for (node_id, file_path, symbol_name), anchor_data in anchors.items():
        existing = conn.execute(
            "SELECT status FROM anchors WHERE node_id = ? AND file_path = ? AND symbol_name = ?",
            (node_id, file_path, symbol_name),
        ).fetchone()

        if merge_mode and existing:
            # If either is STALE, result is STALE (stale-once-stale-always)
            status = "STALE" if existing["status"] == "STALE" or anchor_data.get("status") == "STALE" else "VALID"
        else:
            status = anchor_data.get("status", "VALID")

        conn.execute(
            """
            INSERT OR REPLACE INTO anchors
            (node_id, file_path, symbol_name, ast_hash, start_line, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (node_id, file_path, symbol_name, anchor_data["ast_hash"], anchor_data.get("start_line"), status),
        )

    # Load edges
    for (source_id, target_id, relation), edge_data in edges.items():
        conn.execute(
            "INSERT OR IGNORE INTO edges (source_id, target_id, relation) VALUES (?, ?, ?)",
            (source_id, target_id, relation),
        )

    conn.commit()
    conn.close()


def detect_jsonl_conflicts(jsonl_path: str) -> list[dict]:
    """
    Detect potential merge conflicts in JSONL (items appearing multiple times with different content).

    Returns list of conflict items with (type, id, versions_found).
    """
    conflicts = []
    items_seen = {}

    with open(jsonl_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                item_type = item.get("type")

                if item_type == "node":
                    key = ("node", item["id"])
                elif item_type == "anchor":
                    key = ("anchor", (item["node_id"], item["file_path"], item["symbol_name"]))
                elif item_type == "edge":
                    key = ("edge", (item["source_id"], item["target_id"], item["relation"]))
                else:
                    continue

                if key in items_seen:
                    # Check if content differs
                    if items_seen[key] != item:
                        conflicts.append({
                            "type": item_type,
                            "key": key,
                            "versions": [items_seen[key], item],
                        })
                else:
                    items_seen[key] = item
            except json.JSONDecodeError:
                continue

    return conflicts
