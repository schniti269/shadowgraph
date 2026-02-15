import hashlib
import re
from pathlib import Path

from tree_sitter_language_pack import get_parser

# Map file extensions to tree-sitter language names
LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}

# Tree-sitter node types that represent top-level symbols
SYMBOL_NODE_TYPES: dict[str, list[str]] = {
    "python": ["function_definition", "class_definition"],
    "typescript": ["function_declaration", "class_declaration", "method_definition"],
    "tsx": ["function_declaration", "class_declaration", "method_definition"],
    "javascript": ["function_declaration", "class_declaration", "method_definition"],
}


def compute_ast_hash(node_text: str) -> str:
    """Compute SHA256 of node text stripped of whitespace for formatting-stable hashing."""
    normalized = re.sub(r"\s+", "", node_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_symbol_name(node) -> str | None:
    """Extract the symbol name from a tree-sitter node."""
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "name", "type_identifier"):
            return child.text.decode("utf-8")
    return None


def get_symbol_type_prefix(node_type: str) -> str:
    """Return 'class' or 'function' prefix based on the node type."""
    if "class" in node_type:
        return "class"
    return "function"


def index_file(file_path: str) -> list[dict]:
    """Parse a file and return a list of symbol descriptors.

    Each descriptor contains:
      - symbol_name: e.g., "class:AuthService" or "function:login"
      - content: the full source text of the symbol
      - ast_hash: SHA256 of whitespace-stripped body
      - start_line: 1-based line number
    """
    path = Path(file_path)
    ext = path.suffix
    language = LANG_MAP.get(ext)
    if not language:
        return []

    source_code = path.read_bytes()
    parser = get_parser(language)
    tree = parser.parse(source_code)
    root = tree.root_node

    symbols: list[dict] = []
    target_types = SYMBOL_NODE_TYPES.get(language, [])

    def walk(node):
        if node.type in target_types:
            name = extract_symbol_name(node)
            if name:
                prefix = get_symbol_type_prefix(node.type)
                full_name = f"{prefix}:{name}"
                content = node.text.decode("utf-8")
                ast_hash = compute_ast_hash(content)
                symbols.append(
                    {
                        "symbol_name": full_name,
                        "content": content,
                        "ast_hash": ast_hash,
                        "start_line": node.start_point[0] + 1,  # 1-based
                    }
                )
        for child in node.children:
            walk(child)

    walk(root)
    return symbols
