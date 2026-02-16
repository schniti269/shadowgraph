"""
Serialize SQLite database to JSONL format for git tracking.

Each line is a JSON object representing one node or edge:
- {"type": "node", "id": "...", "node_type": "...", "content": "...", "created_at": "..."}
- {"type": "edge", "source_id": "...", "target_id": "...", "relation": "..."}
- {"type": "anchor", "node_id": "...", "file_path": "...", "symbol_name": "...", "ast_hash": "...", "status": "..."}

This format is:
1. Diffable (one item per line)
2. Mergeable (timestamps prevent conflicts)
3. Git-trackable (human readable)
4. Queryable (can be loaded back into DB)
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime


def serialize_database(db_path: str, output_path: str) -> None:
    """Export database to JSONL format."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    with open(output_path, 'w') as f:
        # Export nodes
        cursor = conn.execute("SELECT * FROM nodes ORDER BY id")
        for row in cursor.fetchall():
            item = {
                "type": "node",
                "id": row["id"],
                "node_type": row["type"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            f.write(json.dumps(item) + "\n")

        # Export anchors
        cursor = conn.execute(
            "SELECT * FROM anchors ORDER BY node_id, file_path, symbol_name"
        )
        for row in cursor.fetchall():
            item = {
                "type": "anchor",
                "node_id": row["node_id"],
                "file_path": row["file_path"],
                "symbol_name": row["symbol_name"],
                "ast_hash": row["ast_hash"],
                "start_line": row["start_line"],
                "status": row["status"],
            }
            f.write(json.dumps(item) + "\n")

        # Export edges
        cursor = conn.execute(
            "SELECT * FROM edges ORDER BY source_id, target_id, relation"
        )
        for row in cursor.fetchall():
            item = {
                "type": "edge",
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "relation": row["relation"],
            }
            f.write(json.dumps(item) + "\n")

    conn.close()


def get_database_checksum(db_path: str) -> str:
    """Compute deterministic checksum of database state for conflict detection."""
    import hashlib

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    hasher = hashlib.sha256()

    # Hash nodes (deterministic order)
    cursor = conn.execute("SELECT id, type, content, created_at FROM nodes ORDER BY id")
    for row in cursor.fetchall():
        hasher.update(f"{row['id']}|{row['type']}|{row['content']}|{row['created_at']}".encode())

    # Hash anchors
    cursor = conn.execute(
        "SELECT node_id, file_path, symbol_name, ast_hash, status FROM anchors ORDER BY node_id, file_path, symbol_name"
    )
    for row in cursor.fetchall():
        hasher.update(f"{row['node_id']}|{row['file_path']}|{row['symbol_name']}|{row['ast_hash']}|{row['status']}".encode())

    # Hash edges
    cursor = conn.execute(
        "SELECT source_id, target_id, relation FROM edges ORDER BY source_id, target_id, relation"
    )
    for row in cursor.fetchall():
        hasher.update(f"{row['source_id']}|{row['target_id']}|{row['relation']}".encode())

    conn.close()
    return hasher.hexdigest()
