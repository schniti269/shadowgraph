from . import DimensionProvider


class KnowledgeDimension(DimensionProvider):
    """Agent-written thoughts, decisions, todos — stored in shadow.db (SQLite)."""

    name = "knowledge"

    def __init__(self, db):
        self._db = db

    def query(self, symbol: str, file_path: str | None, opts: dict) -> dict:
        conn = self._db.conn

        # Thoughts linked to this symbol node
        thoughts = conn.execute(
            """
            SELECT n.id, n.content, n.created_at FROM nodes n
            JOIN edges e ON e.target_id = n.id
            WHERE e.source_id = ? AND n.type = 'THOUGHT'
            ORDER BY n.created_at DESC
            """,
            (symbol,),
        ).fetchall()

        # Business-level context (global knowledge)
        biz = conn.execute(
            """
            SELECT n.id, n.content FROM nodes n
            WHERE n.id LIKE 'business:%' AND n.content LIKE ?
            LIMIT 5
            """,
            (f"%{symbol.split(':')[-1]}%",),
        ).fetchall()

        result = {
            "thoughts": [{"id": dict(r)["id"], "text": dict(r)["content"], "at": dict(r)["created_at"]} for r in thoughts],
        }
        if biz:
            result["business_context"] = [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in biz]
        if not thoughts:
            result["tip"] = "No thoughts yet. Call remember() to attach context."
        return result
