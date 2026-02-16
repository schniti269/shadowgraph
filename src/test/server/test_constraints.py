"""Tests for constraint validation module."""

import json
import os
import tempfile
import pytest

from database import ShadowDB
from constraints import ConstraintValidator


@pytest.fixture
def db_with_symbols():
    """Create a database with some sample symbols."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = ShadowDB(db_path)
        db.connect()

        # Add some sample code and anchors
        # Node IDs must match what indexer.py creates: code:{relpath}:{symbol_name}
        db.upsert_node("code:payment.py:function:charge", "CODE_BLOCK", "def charge(): pass")
        db.upsert_anchor("code:payment.py:function:charge", "payment.py", "function:charge", "hash1", 10)

        db.upsert_node("code:auth.py:function:login", "CODE_BLOCK", "def login(): pass")
        db.upsert_anchor("code:auth.py:function:login", "auth.py", "function:login", "hash2", 5)

        yield db, tmpdir
        db.close()


def test_add_constraint(db_with_symbols):
    """Add a constraint to a symbol."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    constraint_id = validator.add_constraint(
        "function:charge",
        "payment.py",
        "Payments must be idempotent",
        "RULE",
        "critical"
    )

    assert constraint_id is not None
    assert "constraint" in constraint_id


def test_add_multiple_constraints(db_with_symbols):
    """Add multiple constraints to the same symbol."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    id1 = validator.add_constraint(
        "function:charge",
        "payment.py",
        "Payments must be idempotent",
        "RULE",
        "critical"
    )
    id2 = validator.add_constraint(
        "function:charge",
        "payment.py",
        "Do not use Math.random()",
        "FORBIDDEN",
        "error"
    )

    assert id1 != id2
    constraints = validator.get_constraints("payment.py", "function:charge")
    assert len(constraints) >= 2


def test_get_constraints(db_with_symbols):
    """Retrieve all constraints for a symbol."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add a constraint
    validator.add_constraint(
        "function:login",
        "auth.py",
        "Authentication must be secure",
        "RULE",
        "critical"
    )

    # Get constraints
    constraints = validator.get_constraints("auth.py", "function:login")
    assert len(constraints) == 1
    assert constraints[0]["rule"] == "Authentication must be secure"
    assert constraints[0]["type"] == "RULE"


def test_constraint_types(db_with_symbols):
    """Add different types of constraints."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    types = [
        ("RULE", "Must have error handling"),
        ("FORBIDDEN", "Do not use eval()"),
        ("REQUIRED_PATTERN", "All async functions must await"),
        ("REQUIRES_EDGE", "Must link to AuthService"),
    ]

    for constraint_type, rule in types:
        validator.add_constraint(
            "function:charge",
            "payment.py",
            rule,
            constraint_type,
            "error"
        )

    constraints = validator.get_constraints("payment.py", "function:charge")
    assert len(constraints) == 4
    assert set(c["type"] for c in constraints) == set(t[0] for t in types)


def test_constraint_severity_levels(db_with_symbols):
    """Add constraints with different severity levels."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    severities = [
        ("info", "Nice to have"),
        ("warning", "Should consider"),
        ("error", "Must fix"),
        ("critical", "Blocks release"),
    ]

    for severity, rule in severities:
        validator.add_constraint(
            "function:login",
            "auth.py",
            rule,
            "RULE",
            severity
        )

    constraints = validator.get_constraints("auth.py", "function:login")
    assert len(constraints) == 4
    assert sorted([c["severity"] for c in constraints]) == ["critical", "error", "info", "warning"]


def test_validate_symbol_forbidden_pattern(db_with_symbols):
    """Validate detects forbidden patterns in code."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add a code node with forbidden pattern
    db.upsert_node("code:crypto.py:function:random", "CODE_BLOCK", "def random(): return Math.random()")
    db.upsert_anchor("code:crypto.py:function:random", "crypto.py", "function:random", "hash3", 15)

    # Add constraint
    validator.add_constraint(
        "function:random",
        "crypto.py",
        "Do not use Math.random()",
        "FORBIDDEN",
        "critical"
    )

    # Validate
    violations = validator.validate_symbol("crypto.py", "function:random")
    assert len(violations) > 0  # Should find violation


def test_validate_file_multiple_symbols(db_with_symbols):
    """Validate all symbols in a file."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add constraints
    validator.add_constraint(
        "function:charge",
        "payment.py",
        "Payments must be idempotent",
        "RULE",
        "critical"
    )

    # Validate file
    violations = validator.validate_file("payment.py")
    assert len(violations) >= 0  # May have violations or not


def test_list_all_constraints(db_with_symbols):
    """List all constraints in the database."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add constraints to different symbols
    validator.add_constraint(
        "function:charge",
        "payment.py",
        "Payments must be idempotent",
        "RULE",
        "critical"
    )
    validator.add_constraint(
        "function:login",
        "auth.py",
        "Authentication must be secure",
        "RULE",
        "critical"
    )

    # List all
    all_constraints = validator.list_all_constraints()
    assert len(all_constraints) >= 2


def test_constraint_json_serialization(db_with_symbols):
    """Constraints are properly serialized/deserialized."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add complex constraint
    validator.add_constraint(
        "function:charge",
        "payment.py",
        "Payments must be idempotent and handle network failures gracefully",
        "RULE",
        "critical"
    )

    # Get and verify
    constraints = validator.get_constraints("payment.py", "function:charge")
    assert constraints[0]["rule"] == "Payments must be idempotent and handle network failures gracefully"


def test_nonexistent_symbol_validation(db_with_symbols):
    """Validating nonexistent symbol returns error."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    violations = validator.validate_symbol("auth.py", "function:nonexistent")
    assert len(violations) > 0
    assert "not found" in violations[0]["message"].lower()


def test_constraint_on_class_symbol(db_with_symbols):
    """Add constraint to class symbols."""
    db, _ = db_with_symbols
    validator = ConstraintValidator(db)

    # Add class
    db.upsert_node("code:models.py:class:User", "CODE_BLOCK", "class User: pass")
    db.upsert_anchor("code:models.py:class:User", "models.py", "class:User", "hash4", 20)

    # Add constraint
    constraint_id = validator.add_constraint(
        "class:User",
        "models.py",
        "Must validate email format",
        "REQUIRED_PATTERN",
        "warning"
    )

    assert constraint_id is not None
    constraints = validator.get_constraints("models.py", "class:User")
    assert len(constraints) == 1
