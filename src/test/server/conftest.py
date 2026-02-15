import sys
from pathlib import Path

import pytest

# Add server directory to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))

from database import ShadowDB  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary ShadowDB connected to a fresh database."""
    db_path = str(tmp_path / "test.db")
    db = ShadowDB(db_path)
    db.connect()
    yield db
    db.close()


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file for indexing tests."""
    code = tmp_path / "sample.py"
    code.write_text(
        'def hello():\n    return "world"\n\n\nclass Foo:\n    pass\n\n\ndef bar(x):\n    return x + 1\n'
    )
    return str(code)


@pytest.fixture
def sample_typescript_file(tmp_path):
    """Create a sample TypeScript file for indexing tests."""
    code = tmp_path / "sample.ts"
    code.write_text(
        "function greet(name: string): string {\n"
        '    return "hello " + name;\n'
        "}\n\n"
        "class MyService {\n"
        "    run(): void {}\n"
        "}\n"
    )
    return str(code)
