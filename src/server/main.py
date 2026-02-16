import json
import os
import sys
import uuid
import logging
import datetime

# CRITICAL: Never write to stdout in MCP mode — stdout is the JSON-RPC channel.
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logger = logging.getLogger("shadowgraph")

logger.info("=== ShadowGraph MCP Server Starting ===")
logger.info(f"Python version: {sys.version.split()[0]}")

# Use absolute imports so the script works both as `python main.py` and `python -m src.server.main`
sys.path.insert(0, os.path.dirname(__file__))
from database import ShadowDB  # noqa: E402
from indexer import index_file as do_index_file, extract_imports  # noqa: E402
from drift import check_drift as do_check_drift  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

# ============================================================================
# Database initialisation
# Priority: --db-path CLI arg > SHADOW_DB_PATH env var > default
# CLI arg is used because McpStdioServerDefinition may not forward env vars.
# ============================================================================
_db_path_from_arg = None
if "--db-path" in sys.argv:
    _idx = sys.argv.index("--db-path")
    if _idx + 1 < len(sys.argv):
        _db_path_from_arg = sys.argv[_idx + 1]

db_path = _db_path_from_arg or os.environ.get("SHADOW_DB_PATH", ".vscode/shadow.db")
logger.info(f"DB path: {db_path} (source: {'--db-path arg' if _db_path_from_arg else 'env/default'})")

# Workspace root is always two levels above shadow.db: {workspace}/.vscode/shadow.db
_abs_db_path = os.path.abspath(db_path)
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(_abs_db_path))
logger.info(f"Workspace root: {WORKSPACE_ROOT}")
logger.info(f"cwd: {os.getcwd()}")

try:
    db = ShadowDB(_abs_db_path)
    db.connect()
    logger.info(f"Database connected at: {_abs_db_path}")
except Exception as e:
    logger.error(f"CRITICAL: Failed to connect to database: {e}", exc_info=True)
    raise

mcp = FastMCP("ShadowGraph")


# ============================================================================
# Path helpers
# ============================================================================

def _resolve_path(path: str) -> str:
    """Absolute path — relative paths go relative to WORKSPACE_ROOT, not cwd."""
    if os.path.isabs(path):
        return path
    return os.path.join(WORKSPACE_ROOT, path)


def _to_rel_path(path: str) -> str:
    """Forward-slash path relative to WORKSPACE_ROOT. This is what gets stored in the DB."""
    abs_path = _resolve_path(path)
    try:
        rel = os.path.relpath(abs_path, WORKSPACE_ROOT)
    except ValueError:
        rel = abs_path  # Different drive on Windows
    return rel.replace("\\", "/")


# ============================================================================
# THE 5 TOOLS
# ============================================================================

@mcp.tool()
def remember(
    topic: str,
    context: str,
    file_path: str = None,
    symbol_name: str = None,
) -> str:
    """Save knowledge to the graph — WHY code exists, business rules, design decisions.

    *** THIS TOOL DOES NOT CREATE OR EDIT ANY FILES. ***
    Use create_file() to write code to disk.

    This is the single tool for storing ALL knowledge:

    EXAMPLES:
    - Business rule:   remember("shipping", "Always DPD, national only, hub in Berlin")
    - Design decision: remember("why retry", "Added retry to handle flaky payment gateway",
                                file_path="payments.py", symbol_name="function:charge")
    - Before editing:  remember("refactor auth", "Splitting into two functions for testability",
                                file_path="auth.py", symbol_name="class:AuthService")
    - Domain fact:     remember("tracking-api", "Parcel tracking at http://123.22.123.1:7534/parcels")

    Args:
        topic:       Short label for this knowledge (e.g. "why-retry", "pricing-rule", "parcel-api")
        context:     The full explanation. Be specific — include business reason, not just technical what.
        file_path:   Optional. Relative path to a source file to link this to (e.g. "crm/models.py").
        symbol_name: Optional. Symbol in the file to link to (e.g. "function:charge", "class:Customer").
                     Call recall() with no args first to see available symbols if unsure.

    Returns:
        JSON confirmation. Knowledge is now in the graph for future agents and humans.
    """
    logger.debug(f"remember() topic={topic}, file={file_path}, symbol={symbol_name}")

    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    created_at = datetime.datetime.utcnow().isoformat()

    # Store the thought
    db.upsert_node(thought_id, "THOUGHT", context)

    # Link to a code symbol if given
    linked_to = None
    if file_path and symbol_name:
        normalized_path = _to_rel_path(file_path)
        code_node_id = f"code:{normalized_path}:{symbol_name}"
        try:
            db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")
            linked_to = code_node_id
            logger.info(f"Linked thought to {code_node_id}")
        except Exception as e:
            if "FOREIGN KEY" in str(e):
                # Symbol not indexed yet — store business context anyway and warn
                logger.warning(f"Symbol {code_node_id} not indexed yet. Storing thought unlinked.")
                linked_to = f"(unlinked — call index({file_path!r}) first to anchor)"
            else:
                raise

    # Always link to the project business context node for global recall
    project_node_id = "project:business-context"
    db.upsert_node(project_node_id, "CODE_BLOCK", "Project-level business context and domain knowledge")
    topic_node_id = f"business:{topic.lower().replace(' ', '-')}"
    db.upsert_node(topic_node_id, "THOUGHT", f"[{topic}] {context}")
    try:
        db.add_edge(project_node_id, topic_node_id, "HAS_THOUGHT")
        if linked_to and not linked_to.startswith("(unlinked"):
            db.add_edge(linked_to, topic_node_id, "HAS_THOUGHT")
    except Exception:
        pass

    return json.dumps({
        "status": "ok",
        "thought_id": thought_id,
        "topic": topic,
        "linked_to": linked_to,
        "created_at": created_at,
    })


@mcp.tool()
def recall(query: str = "") -> str:
    """Retrieve knowledge from the graph — code context, thoughts, business rules.

    The single tool for reading ALL knowledge. Use it to understand WHY code
    exists before touching it, and to look up business rules.

    EXAMPLES:
    - recall()                   → all business context + recently indexed symbols
    - recall("parcels")          → everything about parcels (code + business rules)
    - recall("function:charge")  → the charge function's code + all linked thoughts
    - recall("crm/models.py")    → all symbols and thoughts in that file

    Args:
        query: What to look up. Can be:
               - Empty / "*"          → all business context + symbol list
               - A symbol name        → "function:charge", "class:Customer"
               - A file path          → "crm/models.py"
               - Any keyword          → searches across all stored knowledge

    Returns:
        JSON with matching code, thoughts, and business context.
    """
    logger.debug(f"recall() query={query!r}")
    q = query.strip()

    results = {
        "query": q or "*",
        "business_context": [],
        "symbols": [],
        "thoughts": [],
    }

    if not q or q == "*":
        # Return ALL business context + list of indexed symbols
        biz_cursor = db.conn.execute(
            """
            SELECT n.id, n.content, n.created_at FROM nodes n
            WHERE (n.id LIKE 'business:%' OR n.id LIKE 'thought:%')
              AND n.type = 'THOUGHT'
              AND n.id IN (SELECT target_id FROM edges WHERE source_id = 'project:business-context')
            ORDER BY n.created_at DESC
            """
        )
        results["business_context"] = [
            {"id": dict(r)["id"], "text": dict(r)["content"]}
            for r in biz_cursor.fetchall()
        ]

        sym_cursor = db.conn.execute(
            """
            SELECT id FROM nodes
            WHERE type = 'CODE_BLOCK' AND id LIKE 'code:%:%'
            ORDER BY created_at DESC LIMIT 30
            """
        )
        results["symbols"] = [dict(r)["id"].split(":", 2)[2] + " (" + dict(r)["id"] + ")"
                              for r in sym_cursor.fetchall()]
        results["tip"] = "Pass a symbol name or keyword to recall() to get full details."
        return json.dumps(results)

    # Try exact code node match first
    exact_id = None
    if q.startswith("code:"):
        exact_id = q
    else:
        # Try as a symbol: code:{file}:{q}
        row = db.conn.execute(
            "SELECT id FROM nodes WHERE id LIKE ? AND type='CODE_BLOCK' LIMIT 1",
            (f"code:%:{q}",)
        ).fetchone()
        if row:
            exact_id = dict(row)["id"]

    if exact_id:
        node = db.get_node(exact_id)
        if node:
            results["symbols"] = [{
                "node_id": exact_id,
                "code": node["content"],
            }]
            thoughts = db.conn.execute(
                """
                SELECT n.id, n.content, n.created_at FROM nodes n
                JOIN edges e ON e.target_id = n.id
                WHERE e.source_id = ? AND n.type = 'THOUGHT'
                ORDER BY n.created_at DESC
                """,
                (exact_id,)
            ).fetchall()
            results["thoughts"] = [{"id": dict(t)["id"], "text": dict(t)["content"]} for t in thoughts]
            if not results["thoughts"]:
                results["tip"] = f"No thoughts linked yet. Use remember(topic, context, file_path, symbol_name) to add context."
            return json.dumps(results)

    # Keyword search: match node IDs and content
    like = f"%{q}%"
    code_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE type='CODE_BLOCK' AND (id LIKE ? OR content LIKE ?) LIMIT 10",
        (like, like)
    ).fetchall()
    results["symbols"] = [{"node_id": dict(r)["id"], "snippet": (dict(r)["content"] or "")[:120]} for r in code_rows]

    thought_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE type='THOUGHT' AND content LIKE ? LIMIT 10",
        (like,)
    ).fetchall()
    results["thoughts"] = [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in thought_rows]

    biz_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE id LIKE 'business:%' AND (id LIKE ? OR content LIKE ?) LIMIT 5",
        (like, like)
    ).fetchall()
    results["business_context"] = [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in biz_rows]

    if not results["symbols"] and not results["thoughts"] and not results["business_context"]:
        results["tip"] = f"Nothing found for '{q}'. Try recall() with no args to see everything that's indexed."

    return json.dumps(results)


@mcp.tool()
def index(file_path: str) -> str:
    """Parse a source file and store all its symbols (functions, classes) in the graph.

    Call this:
    - After creating a new file with create_file()
    - After editing an existing file
    - On any file before calling remember() with a symbol_name from it

    Args:
        file_path: Path to the source file (absolute or relative to project root).
                   Supports Python and TypeScript/JavaScript.

    Returns:
        JSON with the list of symbols now indexed (use these names in remember() and recall()).
    """
    logger.debug(f"index() called with: {file_path}")
    abs_path = _resolve_path(file_path)
    symbols = do_index_file(abs_path)
    relative_path = _to_rel_path(abs_path)
    logger.info(f"Indexed {len(symbols)} symbols from {relative_path}")

    for sym in symbols:
        node_id = f"code:{relative_path}:{sym['symbol_name']}"
        db.upsert_node(node_id, "CODE_BLOCK", sym["content"])
        db.upsert_anchor(
            node_id,
            relative_path,
            sym["symbol_name"],
            sym["ast_hash"],
            sym["start_line"],
        )

    # Extract imports and create DEPENDS_ON edges
    try:
        imports = extract_imports(abs_path)
        for imp in imports:
            import_node_id = f"module:{imp}"
            db.upsert_node(import_node_id, "CODE_BLOCK", f"External module: {imp}")
            file_node_id = f"file:{relative_path}"
            db.upsert_node(file_node_id, "CODE_BLOCK", f"File: {relative_path}")
            db.add_edge(file_node_id, import_node_id, "DEPENDS_ON")
    except Exception as e:
        logger.warning(f"Failed to extract imports: {e}")

    symbol_names = [s["symbol_name"] for s in symbols]
    return json.dumps({
        "status": "ok",
        "file": relative_path,
        "symbols_indexed": len(symbols),
        "symbols": symbol_names,
        "tip": f"Use these symbol names with remember() and recall(), e.g. recall('{symbol_names[0]}')" if symbol_names else "No symbols found (empty file or unsupported language).",
    })


@mcp.tool()
def check(file_path: str = None) -> str:
    """Check for stale thoughts — symbols whose code changed after thoughts were written.

    When code changes but its linked thoughts aren't updated, they become stale.
    Call this after editing files to see what context might be out of date.

    Args:
        file_path: Optional. Path to a specific file to check.
                   Leave empty to check all recently modified files.

    Returns:
        JSON with list of stale symbols and the thoughts that need reviewing.
    """
    logger.debug(f"check() called, file_path={file_path}")

    if file_path:
        abs_path = _resolve_path(file_path)
        stale = do_check_drift(db, abs_path)
        files_checked = [_to_rel_path(abs_path)]
    else:
        # Check all anchored files
        cursor = db.conn.execute("SELECT DISTINCT file_path FROM anchors")
        files_checked = []
        stale = []
        for row in cursor.fetchall():
            fp = dict(row)["file_path"]
            abs_fp = _resolve_path(fp)
            if os.path.exists(abs_fp):
                files_checked.append(fp)
                try:
                    stale.extend(do_check_drift(db, abs_fp))
                except Exception as e:
                    logger.warning(f"check drift failed for {fp}: {e}")

    return json.dumps({
        "status": "ok",
        "files_checked": files_checked,
        "stale_count": len(stale),
        "stale_symbols": stale,
        "tip": "For each stale symbol, call remember() to update the linked context." if stale else "All thoughts are current.",
    })


@mcp.tool()
def create_file(path: str, content: str, language: str = "python") -> str:
    """Create a new file on disk and index its symbols into the graph.

    *** THIS IS THE ONLY TOOL THAT WRITES FILES. ***
    remember(), recall(), index(), and check() do NOT touch the filesystem.

    After creating the file, its symbols are automatically indexed so you can
    immediately use remember() to attach thoughts to them.

    Args:
        path:     File path (absolute, or relative to project root).
                  e.g. "crm/parcel_tracking.py" or "C:/project/src/auth.py"
        content:  The full file content to write.
        language: "python", "typescript", "javascript" (default: "python").
                  Used to determine which symbols to index.

    Returns:
        JSON with the file path, indexed symbols, and a verified_node proving
        the file was written and indexed successfully.
    """
    logger.debug(f"create_file() called for {path}")

    abs_path = _resolve_path(path)
    rel_path = _to_rel_path(abs_path)
    logger.debug(f"Absolute: {abs_path}, relative: {rel_path}")

    try:
        if os.path.exists(abs_path):
            return json.dumps({"status": "error", "message": f"File already exists: {rel_path}. Edit it directly instead."})

        os.makedirs(os.path.dirname(abs_path) or WORKSPACE_ROOT, exist_ok=True)

        # Atomic write
        temp_path = abs_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.rename(temp_path, abs_path)
            logger.info(f"File created: {abs_path} ({os.path.getsize(abs_path)} bytes)")
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

        # Auto-index
        supported = {"python", "typescript", "javascript", "jsx", "tsx"}
        symbols_indexed = 0
        symbol_names = []
        verified = None

        if language.lower() in supported:
            try:
                index_result = json.loads(index(abs_path))
                symbols_indexed = index_result.get("symbols_indexed", 0)
                symbol_names = index_result.get("symbols", [])
                if symbol_names:
                    verified = db.verify_node(f"code:{rel_path}:{symbol_names[0]}")
            except Exception as e:
                logger.warning(f"Auto-index failed: {e}")

        if not verified:
            node_id = f"code:{rel_path}"
            db.upsert_node(node_id, "CODE_BLOCK", content[:500], rel_path)
            verified = db.verify_node(node_id)

        return json.dumps({
            "status": "ok",
            "path": rel_path,
            "symbols_indexed": symbols_indexed,
            "symbols": symbol_names,
            "verified_node": verified,
            "tip": f"File written and indexed. Use remember() to attach context, e.g. remember('why-this-file', 'explanation', file_path='{rel_path}', symbol_name='{symbol_names[0]}')" if symbol_names else f"File written. Call index('{rel_path}') to index symbols after adding code.",
        })
    except Exception as e:
        logger.error(f"create_file failed: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def debug_info() -> str:
    """Diagnostic info: DB path, workspace root, node count. Call if something seems wrong."""
    node_count = 0
    try:
        node_count = db.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    except Exception as e:
        node_count = f"error: {e}"

    return json.dumps({
        "status": "ok",
        "workspace_root": WORKSPACE_ROOT,
        "db_path": _abs_db_path,
        "db_exists": os.path.exists(_abs_db_path),
        "db_size_bytes": os.path.getsize(_abs_db_path) if os.path.exists(_abs_db_path) else 0,
        "node_count": node_count,
        "cwd": os.getcwd(),
        "shadow_db_path_env": os.environ.get("SHADOW_DB_PATH", "(not set)"),
    })


# ============================================================================
# Entry point
# ============================================================================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: main.py --cli <command> [args...]"}))
            sys.exit(1)
        command = sys.argv[2]
        if command == "index" and len(sys.argv) > 3:
            print(index(sys.argv[3]))
        elif command == "check" and len(sys.argv) > 3:
            print(check(sys.argv[3]))
        else:
            print(json.dumps({"error": f"Unknown command: {command}"}))
            sys.exit(1)
    else:
        try:
            logger.info("Starting MCP stdio transport")
            mcp.run(transport="stdio")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
