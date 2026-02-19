import json
import os
import subprocess
from datetime import datetime, timezone

from . import DimensionProvider


def _run(cmd: list[str], cwd: str) -> str:
    """Run a git command, return stdout or empty string on failure."""
    try:
        return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5)
    except Exception:
        return ""


class GitDimension(DimensionProvider):
    """Git history, churn, and authorship — cached in DuckDB (shadow-facts.duckdb)."""

    name = "git"

    def __init__(self, db, workspace_root: str):
        self._db = db
        self._root = workspace_root

    def query(self, symbol: str, file_path: str | None, opts: dict) -> dict:
        if not file_path or not self._db.duck:
            return {"available": False, "reason": "no file_path or DuckDB unavailable"}

        abs_path = os.path.join(self._root, file_path)
        since_days = opts.get("since_days", 90)

        # Check cache validity by file mtime
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            return {"available": False, "reason": "file not found"}

        cached = self._db.duck_query(
            "SELECT content, fact_type FROM git_facts WHERE file_path=? AND symbol_name=? AND file_mtime=?",
            [file_path, symbol, mtime],
        )
        if len(cached) >= 2:
            facts = {r["fact_type"]: json.loads(r["content"]) for r in cached}
            return self._format(facts, cached=True)

        # Fetch fresh from git
        facts = {}

        # Recent commits touching this file
        log = _run(
            ["git", "log", f"--since={since_days} days ago", "--oneline", "--follow", "--", file_path],
            cwd=self._root,
        )
        commits = [line.strip() for line in log.splitlines() if line.strip()]
        facts["commits"] = commits[:20]
        facts["churn"] = len(commits)

        # Authors
        blame_log = _run(
            ["git", "log", "--format=%an", "--follow", "--", file_path],
            cwd=self._root,
        )
        authors = list(dict.fromkeys(l.strip() for l in blame_log.splitlines() if l.strip()))
        facts["authors"] = authors[:10]

        # Cache into DuckDB
        now = datetime.now(timezone.utc).isoformat()
        for fact_type, value in facts.items():
            self._db.duck.execute(
                """
                INSERT OR REPLACE INTO git_facts (file_path, symbol_name, fact_type, content, fetched_at, file_mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [file_path, symbol, fact_type, json.dumps(value), now, mtime],
            )

        return self._format(facts, cached=False)

    def _format(self, facts: dict, cached: bool) -> dict:
        return {
            "churn": facts.get("churn", 0),
            "authors": facts.get("authors", []),
            "recent_commits": facts.get("commits", []),
            "_cached": cached,
        }
