from indexer import index_file
from database import ShadowDB


def check_drift(db: ShadowDB, file_path: str) -> list[dict]:
    """Compare current AST hashes with stored hashes to detect stale notes.

    Returns a list of stale anchors with details about what changed.
    Also updates the anchor status in the database.
    """
    stored_anchors = db.get_anchors_for_file(file_path)
    if not stored_anchors:
        return []

    current_symbols = index_file(file_path)
    current_map = {s["symbol_name"]: s for s in current_symbols}

    stale_results: list[dict] = []

    for anchor in stored_anchors:
        symbol_name = anchor["symbol_name"]
        current = current_map.get(symbol_name)

        if current is None:
            db.mark_stale(anchor["node_id"], file_path, symbol_name)
            stale_results.append(
                {
                    "symbol_name": symbol_name,
                    "status": "DELETED",
                    "message": f"Symbol '{symbol_name}' no longer exists in {file_path}",
                }
            )
        elif current["ast_hash"] != anchor["ast_hash"]:
            db.mark_stale(anchor["node_id"], file_path, symbol_name)
            stale_results.append(
                {
                    "symbol_name": symbol_name,
                    "status": "MODIFIED",
                    "old_hash": anchor["ast_hash"],
                    "new_hash": current["ast_hash"],
                    "message": f"Symbol '{symbol_name}' has been modified since last indexing",
                }
            )

    return stale_results
