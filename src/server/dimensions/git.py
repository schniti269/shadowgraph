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


def _git_available(cwd: str) -> bool:
    """True if cwd is inside a git repo."""
    return bool(_run(["git", "rev-parse", "--git-dir"], cwd=cwd))


class GitDimension(DimensionProvider):
    """Git history, churn, and authorship.

    Always fetches via subprocess. DuckDB caching is optional — if unavailable,
    data is still returned (just re-fetched each call).
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

        if not _git_available(self._root):
            return {"available": False, "reason": "not a git repository"}

        since_days = opts.get("since_days", 90)
        mtime = os.path.getmtime(abs_path)

        # Try DuckDB cache first (optional)
        if self._db.duck:
            cached = self._db.duck_query(
                "SELECT content, fact_type FROM git_facts WHERE file_path=? AND symbol_name=? AND file_mtime=?",
                [file_path, symbol, mtime],
            )
            if len(cached) >= 3:  # commits + churn + authors all cached
                facts = {r["fact_type"]: json.loads(r["content"]) for r in cached}
                return self._format(facts)

        # Fetch from git
        facts = self._fetch(file_path, since_days)

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
                    pass  # Caching is best-effort

        return self._format(facts)

    def _fetch(self, file_path: str, since_days: int) -> dict:
        log = _run(
            ["git", "log", f"--since={since_days} days ago", "--oneline", "--follow", "--", file_path],
            cwd=self._root,
        )
        commits = [l.strip() for l in log.splitlines() if l.strip()]

        blame_log = _run(
            ["git", "log", "--format=%an", "--follow", "--", file_path],
            cwd=self._root,
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
