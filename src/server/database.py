import os
import sqlite3
from pathlib import Path


class ShadowDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        schema_path = Path(__file__).parent / "schema.sql"
        self.conn.executescript(schema_path.read_text())

    def upsert_node(self, node_id: str, node_type: str, content: str, path: str = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO nodes (id, type, content, path) VALUES (?, ?, ?, ?)",
            (node_id, node_type, content, path),
        )
        self.conn.commit()

    def upsert_anchor(
        self,
        node_id: str,
        file_path: str,
        symbol_name: str,
        ast_hash: str,
        start_line: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO anchors
            (node_id, file_path, symbol_name, ast_hash, start_line, status)
            VALUES (?, ?, ?, ?, ?, 'VALID')
            """,
            (node_id, file_path, symbol_name, ast_hash, start_line),
        )
        self.conn.commit()

    def add_edge(self, source_id: str, target_id: str, relation: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO edges (source_id, target_id, relation) VALUES (?, ?, ?)",
            (source_id, target_id, relation),
        )
        self.conn.commit()

    def get_anchors_for_file(self, file_path: str) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM anchors WHERE file_path = ?", (file_path,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_stale_anchors_for_file(self, file_path: str) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM anchors WHERE file_path = ? AND status = 'STALE'",
            (file_path,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_stale(self, node_id: str, file_path: str, symbol_name: str) -> None:
        self.conn.execute(
            """
            UPDATE anchors SET status = 'STALE'
            WHERE node_id = ? AND file_path = ? AND symbol_name = ?
            """,
            (node_id, file_path, symbol_name),
        )
        self.conn.commit()

    def get_thoughts_for_symbol(self, file_path: str, symbol_name: str) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT n.id, n.content, n.created_at FROM nodes n
            JOIN edges e ON e.target_id = n.id
            JOIN anchors a ON a.node_id = e.source_id
            WHERE a.file_path = ? AND a.symbol_name = ? AND n.type = 'THOUGHT'
            ORDER BY n.created_at DESC
            """,
            (file_path, symbol_name),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_node(self, node_id: str) -> dict | None:
        cursor = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def verify_node(self, node_id: str) -> dict | None:
        """Verify a node exists in DB by querying it back (proof of persistence)."""
        cursor = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_folder(self, folder_id: str, path: str, description: str = None) -> None:
        """Create a FOLDER node to represent a module/package."""
        self.upsert_node(folder_id, "FOLDER", description or "", path)

    def get_folder(self, path: str) -> dict | None:
        """Get folder node by path."""
        cursor = self.conn.execute(
            "SELECT * FROM nodes WHERE type = 'FOLDER' AND path = ?", (path,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_folder_contents(self, folder_path: str) -> list[dict]:
        """Get all CODE_BLOCK nodes under a folder path."""
        # Normalize path to end with /
        if not folder_path.endswith('/'):
            folder_path += '/'

        cursor = self.conn.execute(
            """
            SELECT * FROM nodes
            WHERE type = 'CODE_BLOCK' AND path LIKE ?
            ORDER BY path
            """,
            (folder_path + '%',),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_folder_thoughts(self, folder_path: str) -> list[dict]:
        """Get all thoughts attached to a folder."""
        cursor = self.conn.execute(
            """
            SELECT n.id, n.content, n.created_at FROM nodes n
            JOIN edges e ON e.target_id = n.id
            WHERE e.source_id LIKE ? AND n.type = 'THOUGHT'
            ORDER BY n.created_at DESC
            """,
            (f"folder:{folder_path}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
