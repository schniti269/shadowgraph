#!/usr/bin/env python3
"""
ShadowGraph constraint validator for CI/CD pipelines.

Usage:
    graph-check /path/to/shadow.db /path/to/src --fail-on critical

This tool validates all code in the database against defined constraints.
Useful for catching intent violations before they reach production.

Exit codes:
    0: All constraints satisfied (or only warnings/info)
    1: Constraint violations found
    2: Configuration or file error
"""

import json
import sys
import argparse
from pathlib import Path

# Add parent directory to path to import ShadowGraph modules
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'server'))

from database import ShadowDB
from constraints import ConstraintValidator


def main():
    parser = argparse.ArgumentParser(
        description='Validate ShadowGraph constraints for CI/CD',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s shadow.db src/
    %(prog)s shadow.db src/ --fail-on critical
    %(prog)s shadow.db src/ --fail-on error
    %(prog)s shadow.db src/ --json
        """,
    )

    parser.add_argument('db_path', help='Path to shadow.db')
    parser.add_argument('src_path', nargs='?', default='src', help='Source directory to scan (optional)')
    parser.add_argument(
        '--fail-on',
        choices=['critical', 'error', 'warning', 'info'],
        default='critical',
        help='Fail if violations >= this severity (default: critical)',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON instead of human-readable format',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed constraint information',
    )

    args = parser.parse_args()

    # Validate inputs
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f'ERROR: Database not found: {db_path}', file=sys.stderr)
        return 2

    # Connect to database
    try:
        db = ShadowDB(str(db_path))
        db.connect()
    except Exception as e:
        print(f'ERROR: Failed to connect to database: {e}', file=sys.stderr)
        return 2

    # Run validation
    validator = ConstraintValidator(db)

    # Get all anchors and validate
    conn = db.conn
    cursor = conn.execute('SELECT DISTINCT file_path FROM anchors')
    all_files = [row[0] for row in cursor.fetchall()]

    all_violations = []
    for file_path in all_files:
        violations = validator.validate_file(file_path)
        all_violations.extend(violations)

    db.close()

    # Determine severity levels
    severity_rank = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}
    fail_on_rank = severity_rank.get(args.fail_on, 3)

    # Filter violations
    violations_to_report = [
        v for v in all_violations
        if severity_rank.get(v.get('severity', 'info'), 0) >= fail_on_rank
    ]

    # Output results
    if args.json:
        output = {
            'status': 'pass' if not violations_to_report else 'fail',
            'total_violations': len(all_violations),
            'violations_reported': len(violations_to_report),
            'fail_on_severity': args.fail_on,
            'violations': all_violations if args.verbose else violations_to_report,
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        print(f'\n[ShadowGraph Constraint Validator]\n')

        if not all_violations:
            print('✓ No constraint violations found.')
            print(f'  Checked {len(all_files)} files')
            return 0

        print(f'Found {len(all_violations)} total violations:')
        print(f'  Failing ({fail_on_rank}+): {len(violations_to_report)}\n')

        # Group by severity
        for severity in ['critical', 'error', 'warning', 'info']:
            severity_violations = [
                v for v in all_violations
                if v.get('severity') == severity
            ]
            if severity_violations:
                print(f'{severity.upper()}:')
                for v in severity_violations:
                    print(f'  {v.get("symbol", "")}: {v.get("message", "")}')
                print()

    # Exit code
    if violations_to_report:
        print(f'FAILED: {len(violations_to_report)} violations >= {args.fail_on}')
        return 1
    else:
        print('PASSED: All constraints satisfied')
        return 0


if __name__ == '__main__':
    sys.exit(main())
