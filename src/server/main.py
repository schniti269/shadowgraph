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
logger.info(f"Database path: {os.environ.get('SHADOW_DB_PATH', '.vscode/shadow.db')}")
logger.info(f"Python version: {sys.version.split()[0]}")

# Use absolute imports so the script works both as `python main.py` and `python -m src.server.main`
sys.path.insert(0, os.path.dirname(__file__))
from database import ShadowDB  # noqa: E402
from indexer import index_file as do_index_file  # noqa: E402
from drift import check_drift as do_check_drift  # noqa: E402
from serializer import serialize_database  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

# Initialize database
db_path = os.environ.get("SHADOW_DB_PATH", ".vscode/shadow.db")
db = ShadowDB(db_path)
db.connect()

mcp = FastMCP("ShadowGraph")


@mcp.tool()
def index_file(file_path: str) -> str:
    """Index a source file's functions and classes into the ShadowGraph database.

    Parses the file using tree-sitter, identifies all top-level functions and classes,
    computes stable AST hashes (ignoring whitespace), and stores them as CODE_BLOCK
    nodes with anchors in the database.

    Args:
        file_path: Absolute path to the source file to index.

    Returns:
        JSON summary of indexed symbols.
    """
    logger.debug(f"index_file() called with: {file_path}")
    symbols = do_index_file(file_path)
    relative_path = os.path.relpath(file_path)
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

    return json.dumps(
        {
            "status": "ok",
            "file": relative_path,
            "symbols_indexed": len(symbols),
            "symbols": [s["symbol_name"] for s in symbols],
        }
    )


@mcp.tool()
def add_thought(file_path: str, symbol_name: str, thought_text: str) -> str:
    """Add a thought or note linked to a specific function or class.

    The thought is stored as a THOUGHT node in the graph, connected via an
    edge to the CODE_BLOCK node identified by file_path and symbol_name.
    The symbol must have been previously indexed with index_file.

    Args:
        file_path: Relative path to the source file (as stored in the DB).
        symbol_name: Symbol identifier, e.g., "function:login" or "class:AuthService".
        thought_text: The thought, note, or requirement text to attach.

    Returns:
        JSON confirmation with the thought ID and timestamp.
    """
    logger.debug(f"add_thought() called for {file_path}:{symbol_name}")
    code_node_id = f"code:{file_path}:{symbol_name}"
    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    created_at = datetime.datetime.utcnow().isoformat()

    db.upsert_node(thought_id, "THOUGHT", thought_text)
    db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")
    logger.info(f"Thought created: {thought_id} for {code_node_id}")

    return json.dumps(
        {
            "status": "ok",
            "thought_id": thought_id,
            "linked_to": code_node_id,
            "created_at": created_at,
        }
    )


@mcp.tool()
def get_context(file_path: str, symbol_name: str) -> str:
    """Get the full context for a symbol: its source code plus all linked thoughts.

    Useful for an AI agent to understand not just the code, but the developer's
    reasoning, requirements, and notes associated with a symbol.

    Args:
        file_path: Relative path to the source file.
        symbol_name: Symbol identifier, e.g., "function:login".

    Returns:
        JSON object with code content and all linked thoughts.
    """
    code_node_id = f"code:{file_path}:{symbol_name}"

    code_node = db.get_node(code_node_id)
    code_content = code_node["content"] if code_node else None

    thoughts = db.get_thoughts_for_symbol(file_path, symbol_name)

    return json.dumps(
        {
            "symbol": symbol_name,
            "file": file_path,
            "code": code_content,
            "thoughts": [{"id": t["id"], "text": t["content"]} for t in thoughts],
        }
    )


@mcp.tool()
def check_drift(file_path: str) -> str:
    """Compare current AST hashes with stored hashes to detect stale notes.

    Identifies functions or classes that have been modified or deleted since
    they were last indexed. Linked thoughts on modified symbols become 'stale'.

    Args:
        file_path: Absolute path to the source file to check.

    Returns:
        JSON list of stale symbols with details.
    """
    stale = do_check_drift(db, file_path)
    return json.dumps(
        {
            "file": file_path,
            "stale_count": len(stale),
            "stale_symbols": stale,
        }
    )


@mcp.tool()
def edit_code_with_thought(
    file_path: str,
    symbol_name: str,
    thought_text: str,
    new_code: str = ""
) -> str:
    """Edit code while attaching a thought explaining the change.

    This is the recommended way to make code changes when using ShadowGraph.
    By attaching a thought BEFORE making edits, you leave a clear record of
    your reasoning for future developers (and your future self).

    WORKFLOW:
    1. Call this tool FIRST with your explanation of the change
    2. Then use file editing tools to apply the new code
    3. Finally, call index_file() to update the database

    Args:
        file_path: Relative path to the source file.
        symbol_name: Symbol being edited (e.g., "function:login" or "class:AuthService").
        thought_text: Clear explanation of WHY you're making this change.
        new_code: Optional: the new code (for reference only, actual editing is separate).

    Returns:
        JSON confirmation with thought ID. You may now edit the code.
    """
    logger.debug(f"edit_code_with_thought() called for {file_path}:{symbol_name}")
    code_node_id = f"code:{file_path}:{symbol_name}"
    thought_id = f"thought:{uuid.uuid4().hex[:12]}"
    created_at = datetime.datetime.utcnow().isoformat()

    db.upsert_node(thought_id, "THOUGHT", thought_text)
    db.add_edge(code_node_id, thought_id, "HAS_THOUGHT")
    logger.info(f"Edit thought created: {thought_id} for {code_node_id}")

    return json.dumps(
        {
            "status": "ok",
            "thought_id": thought_id,
            "code_node_id": code_node_id,
            "created_at": created_at,
            "message": "Thought recorded. You may now edit the code with your preferred tool.",
            "next_steps": [
                "1. Edit the code using file tools",
                "2. Call index_file() to update the database",
                "3. Call check_drift() if you modified multiple symbols"
            ]
        }
    )


@mcp.tool()
def query_blast_radius(symbol_name: str, depth: int = 2) -> str:
    """Query the blast radius of a symbol: what could break if I change this?

    Recursively retrieves:
    1. Dependencies (outgoing): What does this symbol depend on? What breaks if those change?
    2. Dependents (incoming): Who depends on me? What breaks if I change?
    3. Constraints: What rules apply to this symbol?
    4. Thoughts: What developer notes are attached?

    This is the primary tool for agents to understand impact before making changes.

    Args:
        symbol_name: Symbol identifier, e.g., "function:charge" or "class:PaymentService".
        depth: How many hops to follow (default 2). Higher depth = broader context.

    Returns:
        JSON with blast radius graph including dependencies, dependents, constraints, and thoughts.
    """
    logger.debug(f"query_blast_radius() called for {symbol_name} at depth {depth}")

    # Query database using recursive approach
    conn = db.conn
    conn.row_factory = None  # Use tuple rows for recursive query

    # Recursive CTE to find all reachable nodes (up to depth hops)
    query = """
    WITH RECURSIVE blast(node_id, distance, direction) AS (
        -- Start: find the target node by symbol_name pattern
        SELECT n.id, 0, 'root'
        FROM nodes n
        WHERE n.id LIKE ?

        UNION ALL

        -- Outgoing: what does this depend on?
        SELECT e.target_id, b.distance + 1, 'depends_on'
        FROM blast b
        JOIN edges e ON e.source_id = b.node_id
        WHERE b.distance < ? AND e.relation IN ('DEPENDS_ON', 'HAS_THOUGHT')

        UNION ALL

        -- Incoming: who depends on this?
        SELECT e.source_id, b.distance + 1, 'depended_by'
        FROM blast b
        JOIN edges e ON e.target_id = b.node_id
        WHERE b.distance < ? AND e.relation IN ('DEPENDS_ON', 'REQUIRED_BY')
    )
    SELECT DISTINCT b.node_id, b.distance, b.direction, n.type, n.content
    FROM blast b
    JOIN nodes n ON n.id = b.node_id
    ORDER BY b.distance, b.direction, b.node_id
    """

    # Find root node by symbol name pattern
    pattern = f"%:{symbol_name}" if ":" not in symbol_name else f"%{symbol_name}%"

    cursor = conn.execute(query, (pattern, depth, depth))
    results = cursor.fetchall()

    # Format results
    dependencies = []
    dependents = []
    root_thoughts = []

    for node_id, distance, direction, node_type, content in results:
        if distance == 0:
            # This is the root node we're analyzing
            root_node = {
                "id": node_id,
                "type": node_type,
                "content": content[:200] if content else None,  # Snippet
            }
        elif direction == "depends_on" and node_type != "THOUGHT":
            dependencies.append({
                "id": node_id,
                "type": node_type,
                "distance": distance,
                "content": content[:100] if content else None,
            })
        elif direction == "depends_on" and node_type == "THOUGHT":
            root_thoughts.append({
                "id": node_id,
                "text": content,
            })
        elif direction in ("depended_by", "root") and node_type != "THOUGHT":
            dependents.append({
                "id": node_id,
                "type": node_type,
                "distance": distance,
                "content": content[:100] if content else None,
            })

    logger.info(f"Blast radius for {symbol_name}: {len(dependencies)} deps, {len(dependents)} dependents")

    return json.dumps(
        {
            "symbol": symbol_name,
            "depth": depth,
            "root": root_node if results else None,
            "dependencies": dependencies,
            "dependents": dependents,
            "thoughts": root_thoughts,
            "summary": f"Found {len(dependencies)} dependencies, {len(dependents)} dependents at depth {depth}",
        }
    )


@mcp.tool()
def serialize_graph(output_path: str = ".shadow/graph.jsonl") -> str:
    """Export the semantic graph to JSONL format for git tracking.

    Creates a `.shadow/graph.jsonl` file with all nodes, anchors, and edges
    in JSONL format (one JSON object per line). This file is designed to be:
    - Diffable (line-based diffs)
    - Mergeable (timestamps prevent conflicts)
    - Git-trackable (human readable)
    - Loadable back into the database via deserialize_graph()

    Args:
        output_path: Where to write the JSONL file (default: .shadow/graph.jsonl).

    Returns:
        JSON confirmation with file size and item counts.
    """
    logger.debug(f"serialize_graph() called, output to {output_path}")

    # Create .shadow directory if needed
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    serialize_database(db_path, output_path)

    # Count items
    conn = db.conn
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    anchor_count = conn.execute("SELECT COUNT(*) FROM anchors").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

    logger.info(f"Graph serialized to {output_path}: {node_count} nodes, {anchor_count} anchors, {edge_count} edges")

    return json.dumps(
        {
            "status": "ok",
            "output_path": output_path,
            "file_size_bytes": file_size,
            "nodes": node_count,
            "anchors": anchor_count,
            "edges": edge_count,
            "message": f"Graph exported. Commit {output_path} to git to share with your team.",
        }
    )


# Entry point
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # CLI mode for direct invocation from the VS Code extension
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: main.py --cli <command> [args...]"}))
            sys.exit(1)
        command = sys.argv[2]
        if command == "index_file" and len(sys.argv) > 3:
            result = index_file(sys.argv[3])
            print(result)
        elif command == "check_drift" and len(sys.argv) > 3:
            result = check_drift(sys.argv[3])
            print(result)
        elif command == "serialize_graph":
            output = sys.argv[3] if len(sys.argv) > 3 else ".shadow/graph.jsonl"
            result = serialize_graph(output)
            print(result)
        else:
            print(json.dumps({"error": f"Unknown command or missing args: {command}"}))
            sys.exit(1)
    else:
        # MCP stdio mode (default)
        try:
            logger.info("Starting MCP stdio transport")
            mcp.run(transport="stdio")
            logger.info("MCP stdio transport exited normally")
        except Exception as e:
            logger.error(f"Fatal error in MCP server: {e}", exc_info=True)
            sys.exit(1)
