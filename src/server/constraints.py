"""
Constraint validation and management for ShadowGraph.

Constraints are rules that code must follow:
- RULE: General requirement (e.g., "Payments must be idempotent")
- FORBIDDEN: Patterns to avoid (e.g., "Do not use Math.random() for security")
- REQUIRED_PATTERN: Code must match a pattern (e.g., "All async funcs have error handling")
- REQUIRES_EDGE: Semantic relationship required (e.g., "Session mgmt links to AuthService")

Constraints are attached to symbols and validated against code changes.
"""

import json
import uuid
from typing import Optional
from database import ShadowDB


class ConstraintValidator:
    """Validates code against defined constraints."""

    def __init__(self, db: ShadowDB):
        self.db = db

    def add_constraint(
        self,
        symbol_name: str,
        file_path: str,
        rule_text: str,
        constraint_type: str = "RULE",
        severity: str = "warning",
    ) -> str:
        """Add a constraint to a symbol.

        Args:
            symbol_name: Symbol to constrain (e.g., "function:charge")
            file_path: File containing the symbol
            rule_text: The constraint description
            constraint_type: Type: RULE, FORBIDDEN, REQUIRED_PATTERN, REQUIRES_EDGE
            severity: warning, error, critical

        Returns:
            Constraint node ID
        """
        # Use unique constraint ID to avoid collisions
        constraint_id = f"constraint:{uuid.uuid4().hex[:8]}"

        # Store constraint as a node FIRST
        constraint_content = json.dumps({
            "type": constraint_type,
            "rule": rule_text,
            "severity": severity,
            "symbol_name": symbol_name,
            "file_path": file_path,
        })

        self.db.upsert_node(constraint_id, "REQUIREMENT", constraint_content)

        # Link constraint to symbol (source -> target means "code requires constraint")
        code_node_id = f"code:{file_path}:{symbol_name}"
        self.db.add_edge(code_node_id, constraint_id, "REQUIRED_BY")

        return constraint_id

    def get_constraints(self, file_path: str, symbol_name: str) -> list[dict]:
        """Get all constraints for a symbol."""
        code_node_id = f"code:{file_path}:{symbol_name}"

        conn = self.db.conn
        cursor = conn.execute(
            """
            SELECT n.id, n.content FROM nodes n
            JOIN edges e ON e.target_id = n.id
            WHERE e.source_id = ? AND e.relation = 'REQUIRED_BY' AND n.type = 'REQUIREMENT'
            """,
            (code_node_id,),
        )

        constraints = []
        for row in cursor.fetchall():
            try:
                content = json.loads(row[1]) if row[1] else {}
                constraints.append({
                    "id": row[0],
                    "type": content.get("type", "RULE"),
                    "rule": content.get("rule", ""),
                    "severity": content.get("severity", "warning"),
                })
            except json.JSONDecodeError:
                constraints.append({
                    "id": row[0],
                    "type": "RULE",
                    "rule": row[1] or "",
                    "severity": "warning",
                })

        return constraints

    def validate_symbol(self, file_path: str, symbol_name: str) -> list[dict]:
        """Validate a symbol against its constraints.

        Returns list of violations with (severity, message).
        This is a basic implementation; real validation would check code patterns.
        """
        constraints = self.get_constraints(file_path, symbol_name)
        violations = []

        # Get the code node
        code_node_id = f"code:{file_path}:{symbol_name}"
        code_node = self.db.get_node(code_node_id)

        if not code_node:
            return [{"severity": "error", "message": f"Symbol not found: {symbol_name}"}]

        code_content = code_node.get("content", "")

        for constraint in constraints:
            # Simple pattern matching (real validation would be more sophisticated)
            constraint_type = constraint.get("type", "RULE")
            rule = constraint.get("rule", "")
            severity = constraint.get("severity", "warning")

            # FORBIDDEN: Check if pattern appears in code (very naive)
            if constraint_type == "FORBIDDEN":
                # Extract the pattern from rule text (assume first word or quoted string)
                pattern = rule.split("'")[1] if "'" in rule else rule.split()[-1] if rule.split() else ""
                if pattern and pattern.lower() in code_content.lower():
                    violations.append({
                        "severity": severity,
                        "symbol": symbol_name,
                        "constraint_type": constraint_type,
                        "message": f"Violation: {rule}",
                    })

            # RULE: Just log it (would need specific checks for each rule)
            elif constraint_type == "RULE":
                # Log as info (rules are informational unless they have "must" language)
                if " must " in rule.lower() or " required " in rule.lower():
                    violations.append({
                        "severity": "info",
                        "symbol": symbol_name,
                        "constraint_type": constraint_type,
                        "message": f"Applies: {rule}",
                    })

        return violations

    def validate_file(self, file_path: str) -> list[dict]:
        """Validate all symbols in a file against their constraints."""
        anchors = self.db.get_anchors_for_file(file_path)
        all_violations = []

        for anchor in anchors:
            symbol_name = anchor["symbol_name"]
            violations = self.validate_symbol(file_path, symbol_name)
            all_violations.extend(violations)

        return all_violations

    def list_all_constraints(self) -> list[dict]:
        """List all constraints in the database."""
        conn = self.db.conn
        cursor = conn.execute(
            "SELECT id, content FROM nodes WHERE type = 'REQUIREMENT'"
        )

        constraints = []
        for row in cursor.fetchall():
            try:
                content = json.loads(row[1]) if row[1] else {}
                constraints.append({
                    "id": row[0],
                    "type": content.get("type", "RULE"),
                    "rule": content.get("rule", ""),
                    "severity": content.get("severity", "warning"),
                })
            except json.JSONDecodeError:
                constraints.append({
                    "id": row[0],
                    "type": "RULE",
                    "rule": row[1] or "",
                    "severity": "warning",
                })

        return constraints
