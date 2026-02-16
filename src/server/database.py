import os
import sqlite3
import uuid
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

        # Migration: Apply before schema creation to handle old databases
        self._apply_migrations()

        schema_path = Path(__file__).parent / "schema.sql"
        self.conn.executescript(schema_path.read_text())

    def _apply_migrations(self) -> None:
        """Apply schema migrations for existing databases."""
        # Check if nodes table exists (skip migrations for fresh DB)
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        )
        if not cursor.fetchone():
            return  # Fresh database, no migrations needed

        cursor = self.conn.execute("PRAGMA table_info(nodes)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add path column if missing
        if "path" not in columns:
            try:
                self.conn.execute("ALTER TABLE nodes ADD COLUMN path TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Fix CHECK constraint to include FOLDER and CONSTRAINT types
        # Old DBs reject FOLDER inserts. Recreate the table with updated constraint.
        try:
            # Check if a FOLDER insert would fail
            self.conn.execute(
                "INSERT INTO nodes (id, type, content) VALUES (?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (f"_migration_test_{uuid.uuid4().hex[:8]}", "FOLDER", "test")
            )
            self.conn.execute(
                "DELETE FROM nodes WHERE id LIKE '_migration_test%'"
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            # CHECK constraint failed — need to recreate table
            # Backup existing data, recreate with new constraint, restore
            self.conn.execute("PRAGMA foreign_keys=OFF")

            # Copy existing data to temp table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes_backup (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    content TEXT,
                    vector BLOB,
                    path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("INSERT INTO nodes_backup SELECT * FROM nodes")

            # Drop old table (will cascade delete anchors due to FK)
            self.conn.execute("DROP TABLE nodes")

            # Recreate with fixed CHECK constraint (includes FOLDER, CONSTRAINT)
            self.conn.executescript(Path(__file__).parent.joinpath("schema.sql").read_text())

            # Restore data
            self.conn.execute("""
                INSERT INTO nodes (id, type, content, vector, path, created_at)
                SELECT id, type, content, vector, path, created_at FROM nodes_backup
            """)
            self.conn.execute("DROP TABLE nodes_backup")

            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.commit()

        # Add indexes if they don't exist (safe due to IF NOT EXISTS)
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)",
            "CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path)",
        ]
        for index_sql in indexes:
            try:
                self.conn.execute(index_sql)
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Index already exists

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
