from indexer import index_file, compute_ast_hash


def test_index_python_file(sample_python_file):
    """Test that indexing a Python file extracts functions and classes."""
    symbols = index_file(sample_python_file)
    names = [s["symbol_name"] for s in symbols]
    assert "function:hello" in names
    assert "class:Foo" in names
    assert "function:bar" in names


def test_index_python_start_lines(sample_python_file):
    """Test that start lines are correct (1-based)."""
    symbols = index_file(sample_python_file)
    by_name = {s["symbol_name"]: s for s in symbols}
    assert by_name["function:hello"]["start_line"] == 1
    assert by_name["class:Foo"]["start_line"] == 5
    assert by_name["function:bar"]["start_line"] == 9


def test_index_typescript_file(sample_typescript_file):
    """Test that indexing a TypeScript file extracts functions and classes."""
    symbols = index_file(sample_typescript_file)
    names = [s["symbol_name"] for s in symbols]
    assert "function:greet" in names
    assert "class:MyService" in names


def test_index_unsupported_extension(tmp_path):
    """Test that unsupported file types return empty list."""
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}')
    symbols = index_file(str(f))
    assert symbols == []


def test_hash_stability(sample_python_file):
    """Test that hashing the same code twice produces the same hash."""
    symbols1 = index_file(sample_python_file)
    symbols2 = index_file(sample_python_file)
    for s1, s2 in zip(symbols1, symbols2):
        assert s1["ast_hash"] == s2["ast_hash"]


def test_hash_whitespace_insensitive():
    """Test that whitespace changes don't affect the hash."""
    code1 = "def hello():\n    return 'world'"
    code2 = "def hello():\n        return 'world'"
    assert compute_ast_hash(code1) == compute_ast_hash(code2)


def test_hash_changes_on_code_change():
    """Test that a substantive code change alters the hash."""
    code1 = "def hello():\n    return 'world'"
    code2 = "def hello():\n    return 'universe'"
    assert compute_ast_hash(code1) != compute_ast_hash(code2)
