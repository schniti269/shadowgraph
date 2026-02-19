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
from dimensions.knowledge import KnowledgeDimension  # noqa: E402
from dimensions.git import GitDimension  # noqa: E402

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

# Dimension providers — keyed by name for O(1) lookup
_PROVIDERS = {
    "knowledge": KnowledgeDimension(db),
    "git": GitDimension(db, WORKSPACE_ROOT),
}
_ALL_DIMENSIONS = list(_PROVIDERS.keys())


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
def recall(
    query: str = "",
    dimensions: list[str] = None,
    depth: int = 1,
    filter: dict = None,
) -> str:
    """Retrieve knowledge across multiple dimensions — code, history, thoughts, dependencies.

    This replaces read_file, git_log, grep, find_references. ONE call.

    EXAMPLES:
    - recall()                                    → all business context + indexed symbols
    - recall("function:charge")                   → symbol + all knowledge thoughts
    - recall("function:charge", ["knowledge","git"]) → thoughts + git history/churn
    - recall("crm/models.py", depth=2)            → file + parent folder context
    - recall("payment", filter={"since_days":30}) → payment symbols, git limited to 30 days

    Args:
        query:      Symbol name ("function:charge"), file path ("crm/models.py"), or keyword.
                    Empty → list all indexed symbols + business context.
        dimensions: Which dimensions to query. Default: all available.
                    Options: "knowledge", "git"  (more coming: "syntax", "refs")
        depth:      1 = symbol only, 2 = include parent class/file context too.
        filter:     Cross-dimension options: {"since_days": 30}

    Returns:
        JSON with symbol location + one key per requested dimension.
    """
    logger.debug(f"recall() query={query!r} dimensions={dimensions} depth={depth} filter={filter}")
    q = query.strip()
    opts = filter or {}
    requested = dimensions if dimensions is not None else _ALL_DIMENSIONS

    # ── Empty query: index listing ─────────────────────────────────────────
    if not q or q == "*":
        biz = db.conn.execute(
            """
            SELECT n.id, n.content FROM nodes n
            WHERE n.type = 'THOUGHT'
              AND n.id IN (SELECT target_id FROM edges WHERE source_id = 'project:business-context')
            ORDER BY n.created_at DESC
            """
        ).fetchall()
        syms = db.conn.execute(
            "SELECT id FROM nodes WHERE type='CODE_BLOCK' AND id LIKE 'code:%:%' ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        return json.dumps({
            "query": "*",
            "business_context": [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in biz],
            "symbols": [dict(r)["id"].split(":", 2)[2] + " (" + dict(r)["id"] + ")" for r in syms],
            "tip": "Pass a symbol name or keyword to get full details across dimensions.",
        })

    # ── Resolve to a node_id ───────────────────────────────────────────────
    node_id = None
    file_path = None

    if q.startswith("code:"):
        node_id = q
    else:
        row = db.conn.execute(
            "SELECT id FROM nodes WHERE id LIKE ? AND type='CODE_BLOCK' LIMIT 1",
            (f"code:%:{q}",),
        ).fetchone()
        if row:
            node_id = dict(row)["id"]

    if node_id:
        # Extract file_path from node_id: code:{file}:{symbol}
        parts = node_id.split(":", 2)
        if len(parts) == 3:
            file_path = parts[1]

    # ── Fan out to dimension providers ────────────────────────────────────
    if node_id:
        node = db.get_node(node_id)
        result = {
            "query": q,
            "node_id": node_id,
            "location": f"{file_path}:{node_id.split(':')[-1]}" if file_path else node_id,
            "dimensions": {},
        }
        for dim_name in requested:
            provider = _PROVIDERS.get(dim_name)
            if provider:
                try:
                    result["dimensions"][dim_name] = provider.query(node_id, file_path, opts)
                except Exception as e:
                    logger.warning(f"Dimension {dim_name} failed: {e}")
                    result["dimensions"][dim_name] = {"error": str(e)}

        # depth=2: also include parent class/file context
        if depth >= 2 and file_path:
            file_node_id = f"file:{file_path}"
            parent = db.get_node(file_node_id)
            if parent:
                result["parent_file"] = {"node_id": file_node_id}
                for dim_name in requested:
                    provider = _PROVIDERS.get(dim_name)
                    if provider:
                        try:
                            result["parent_file"][dim_name] = provider.query(file_node_id, file_path, opts)
                        except Exception:
                            pass

        return json.dumps(result)

    # ── Keyword fallback ───────────────────────────────────────────────────
    like = f"%{q}%"
    code_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE type='CODE_BLOCK' AND (id LIKE ? OR content LIKE ?) LIMIT 10",
        (like, like),
    ).fetchall()
    thought_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE type='THOUGHT' AND content LIKE ? LIMIT 10",
        (like,),
    ).fetchall()
    biz_rows = db.conn.execute(
        "SELECT id, content FROM nodes WHERE id LIKE 'business:%' AND (id LIKE ? OR content LIKE ?) LIMIT 5",
        (like, like),
    ).fetchall()

    result = {
        "query": q,
        "symbols": [{"node_id": dict(r)["id"], "snippet": (dict(r)["content"] or "")[:120]} for r in code_rows],
        "thoughts": [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in thought_rows],
        "business_context": [{"id": dict(r)["id"], "text": dict(r)["content"]} for r in biz_rows],
    }
    if not any(result[k] for k in ("symbols", "thoughts", "business_context")):
        result["tip"] = f"Nothing found for '{q}'. Try recall() with no args to see everything indexed."
    return json.dumps(result)


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
def edit(file_path: str, symbol_name: str, thought: str, new_code: str) -> str:
    """Edit a symbol's code — but you MUST explain WHY first.

    This is the only tool that modifies existing files. It atomically:
    1. Writes your thought to the knowledge graph (the WHY)
    2. Replaces the symbol's code in the file
    3. Re-indexes the file so the graph stays current

    If any step fails the file is rolled back. No silent half-writes.

    Args:
        file_path:   Relative path to the file (e.g. "src/billing/stripe.py").
        symbol_name: Prefixed symbol to replace (e.g. "function:charge", "class:Customer").
                     Call recall(file_path) first to see valid symbol names.
        thought:     WHY you are making this change. Be specific — business reason, not just what.
        new_code:    The complete new source code for this symbol only (not the whole file).

    Returns:
        JSON with thought_id, new AST hash, and confirmation the file was updated.
    """
    logger.debug(f"edit() file={file_path} symbol={symbol_name}")

    abs_path = _resolve_path(file_path)
    rel_path = _to_rel_path(abs_path)

    # 1. Verify symbol is indexed
    node_id = f"code:{rel_path}:{symbol_name}"
    anchor_rows = db.conn.execute(
        "SELECT start_line, ast_hash FROM anchors WHERE node_id=? AND status='VALID'",
        (node_id,),
    ).fetchall()
    if not anchor_rows:
        return json.dumps({
            "status": "error",
            "message": f"Symbol '{symbol_name}' not found in index for {rel_path}. Call index('{rel_path}') first, then recall() to confirm the symbol name.",
        })

    anchor = dict(anchor_rows[0])
    start_line = anchor["start_line"]

    # 2. Read file, find the symbol block to replace
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            original = f.read()
    except OSError as e:
        return json.dumps({"status": "error", "message": f"Cannot read file: {e}"})

    lines = original.splitlines(keepends=True)

    # Find the symbol start line (1-indexed) and determine its extent via indentation
    if start_line < 1 or start_line > len(lines):
        return json.dumps({"status": "error", "message": f"start_line {start_line} out of range for {rel_path}"})

    # Determine block end: collect lines while indented past the definition line
    def_indent = len(lines[start_line - 1]) - len(lines[start_line - 1].lstrip())
    end_line = start_line
    for i in range(start_line, len(lines)):
        stripped = lines[i].lstrip()
        if i == start_line - 1 or not stripped or len(lines[i]) - len(stripped) > def_indent:
            end_line = i + 1
        elif i > start_line - 1:
            break

    # 3. Write thought BEFORE touching the file
    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    db.upsert_node(thought_id, "THOUGHT", thought)
    try:
        db.add_edge(node_id, thought_id, "HAS_THOUGHT")
    except Exception as e:
        logger.warning(f"Could not link thought to node: {e}")

    # 4. Atomic file rewrite with rollback
    backup = abs_path + ".bak"
    try:
        with open(backup, "w", encoding="utf-8") as f:
            f.write(original)

        new_lines = lines[:start_line - 1] + [new_code if new_code.endswith("\n") else new_code + "\n"] + lines[end_line:]
        temp_path = abs_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.replace(temp_path, abs_path)
        logger.info(f"edit() wrote {rel_path} (replaced lines {start_line}-{end_line})")
    except Exception as e:
        # Rollback
        if os.path.exists(backup):
            os.replace(backup, abs_path)
        return json.dumps({"status": "error", "message": f"File write failed, rolled back: {e}"})
    finally:
        if os.path.exists(backup):
            os.remove(backup)

    # 5. Re-index to update AST hash
    try:
        idx = json.loads(index(abs_path))
        new_symbols = idx.get("symbols", [])
    except Exception as e:
        logger.warning(f"Re-index after edit failed: {e}")
        new_symbols = []

    # 6. Verify new hash stored
    updated_anchor = db.conn.execute(
        "SELECT ast_hash, status FROM anchors WHERE node_id=?", (node_id,)
    ).fetchone()
    new_hash = dict(updated_anchor)["ast_hash"] if updated_anchor else None

    return json.dumps({
        "status": "ok",
        "file": rel_path,
        "symbol": symbol_name,
        "thought_id": thought_id,
        "new_ast_hash": new_hash,
        "symbols_reindexed": new_symbols,
    })


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
