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


def _find_git_root(start: str) -> str | None:
    """Walk up from start until we find a .git directory. Returns the git root or None."""
    current = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root
            return None
        current = parent


class GitDimension(DimensionProvider):
    """Git history, churn, and authorship.

    Searches for the git root by walking up from the queried file — works regardless
    of whether the git repo root matches the workspace root.
    DuckDB caching is best-effort: if unavailable, data is still returned.
    """

    name = "git"

    def __init__(self, db, workspace_root: str):
        self._db = db
        self._root = workspace_root

    def query(self, symbol: str, file_path: str | None, opts: dict) -> dict:
        if not file_path:
            return {"available": False, "reason": "no file_path"}

        abs_path = os.path.join(self._root, file_path)
        if not os.path.exists(abs_path):
            return {"available": False, "reason": "file not found"}

        # Find git root by walking up from the file (not just from workspace root)
        git_root = _find_git_root(os.path.dirname(abs_path))
        if not git_root:
            return {"available": False, "reason": "not a git repository"}

        # Path relative to git root — what git commands expect
        try:
            git_rel = os.path.relpath(abs_path, git_root).replace("\\", "/")
        except ValueError:
            git_rel = file_path  # different drive on Windows

        since_days = opts.get("since_days", 90)
        mtime = os.path.getmtime(abs_path)

        # Try DuckDB cache first (optional)
        if self._db.duck:
            cached = self._db.duck_query(
                "SELECT content, fact_type FROM git_facts WHERE file_path=? AND symbol_name=? AND file_mtime=?",
                [file_path, symbol, mtime],
            )
            if len(cached) >= 3:
                facts = {r["fact_type"]: json.loads(r["content"]) for r in cached}
                return self._format(facts)

        facts = self._fetch(git_root, git_rel, since_days)

        # Cache in DuckDB if available
        if self._db.duck:
            now = datetime.now(timezone.utc).isoformat()
            for fact_type, value in facts.items():
                try:
                    self._db.duck.execute(
                        """
                        INSERT OR REPLACE INTO git_facts
                        (file_path, symbol_name, fact_type, content, fetched_at, file_mtime)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [file_path, symbol, fact_type, json.dumps(value), now, mtime],
                    )
                except Exception:
                    pass

        return self._format(facts)

    def _fetch(self, git_root: str, git_rel: str, since_days: int) -> dict:
        log = _run(
            ["git", "log", f"--since={since_days} days ago", "--oneline", "--follow", "--", git_rel],
            cwd=git_root,
        )
        commits = [l.strip() for l in log.splitlines() if l.strip()]

        blame_log = _run(
            ["git", "log", "--format=%an", "--follow", "--", git_rel],
            cwd=git_root,
        )
        authors = list(dict.fromkeys(l.strip() for l in blame_log.splitlines() if l.strip()))

        return {
            "commits": commits[:20],
            "churn": len(commits),
            "authors": authors[:10],
        }

    def _format(self, facts: dict) -> dict:
        return {
            "churn": facts.get("churn", 0),
            "authors": facts.get("authors", []),
            "recent_commits": facts.get("commits", []),
        }
