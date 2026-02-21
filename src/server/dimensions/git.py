import json
import os
import subprocess
from datetime import datetime, timezone

from . import DimensionProvider


def _run(cmd: list[str], cwd: str) -> str:
    """Run a git command, return stdout or empty string on failure.

    Uses Popen directly to avoid Windows pipe-cleanup hangs after timeout.
    CREATE_NO_WINDOW suppresses the console flash on Windows.
    """
    try:
        kwargs: dict = {}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", **kwargs,
        )
        try:
            stdout, _ = proc.communicate(timeout=4)
            return stdout
        except subprocess.TimeoutExpired:
            proc.kill()
            return ""  # don't call communicate() again — avoids Windows cleanup hang
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

        git_root = _find_git_root(os.path.dirname(abs_path))
        if not git_root:
            return {"available": False, "reason": "not a git repository"}

        try:
            git_rel = os.path.relpath(abs_path, git_root).replace("\\", "/")
        except ValueError:
            git_rel = file_path

        # Symbol-level query: "code:{file}:{type}:{name}" — use git log -L for function history
        parts = symbol.split(":")
        if len(parts) >= 4 and parts[0] == "code":
            symbol_name = parts[-1]  # e.g., "predict" from "code:src/model.py:function:predict"
            return self._symbol_history(git_root, git_rel, symbol_name)

        # File-level query — chronological diff history
        since_days = opts.get("since_days", 90)
        return self._file_history(git_root, git_rel, since_days)

    def _symbol_history(self, git_root: str, git_rel: str, symbol_name: str) -> dict:
        """Chronological evolution of a single symbol using git log -L :<func>:<file>."""
        raw = _run(
            [
                "git", "log",
                "--max-count=20",
                "--reverse",
                "--date=short",
                f"-L:{symbol_name}:{git_rel}",
            ],
            cwd=git_root,
        )
        if not raw:
            # Fallback: git doesn't know how to locate the symbol (language not supported)
            return {"available": False, "reason": f"git could not track symbol '{symbol_name}' in {git_rel}"}

        return self._parse_L_output(raw)

    def _parse_L_output(self, raw: str) -> dict:
        """Parse git log -L output into a structured chronological history."""
        entries: list[dict] = []
        current: dict | None = None
        diff_lines: list[str] = []
        in_diff = False

        for line in raw.splitlines():
            if line.startswith("commit "):
                if current is not None:
                    current["diff"] = "\n".join(diff_lines)
                    entries.append(current)
                current = {"commit": line[7:14], "author": "", "date": "", "message": "", "diff": ""}
                diff_lines = []
                in_diff = False
            elif current is None:
                continue
            elif line.startswith("Author: "):
                current["author"] = line[8:].split("<")[0].strip()
            elif line.startswith("Date:   "):
                current["date"] = line[8:].strip()
            elif line.startswith("    ") and not in_diff:
                msg = line.strip()
                if msg and not current["message"]:
                    current["message"] = msg
            elif line.startswith("@@"):
                in_diff = True
                diff_lines.append(line)
            elif in_diff and line and line[0] in ("+", "-", " ", "\\"):
                diff_lines.append(line[:120])  # cap line length

        if current is not None:
            current["diff"] = "\n".join(diff_lines)
            entries.append(current)

        authors = list(dict.fromkeys(e["author"] for e in entries if e["author"]))
        return {
            "churn": len(entries),
            "authors": authors,
            "history": entries,  # oldest → newest (--reverse)
        }

    def _file_history(self, git_root: str, git_rel: str, since_days: int) -> dict:
        """Chronological diff history for a whole file."""
        raw = _run(
            [
                "git", "log",
                f"--since={since_days} days ago",
                "--max-count=20",
                "--reverse",
                "--date=short",
                "--unified=2",
                "-p",
                "--follow",
                "--",
                git_rel,
            ],
            cwd=git_root,
        )
        if not raw:
            return {"history": [], "churn": 0, "authors": []}
        return self._parse_L_output(raw)

    # File suffixes and path prefixes that are generated/binary — not useful signal for agents.
    _NOISE_SUFFIXES = frozenset({
        ".db", ".db-shm", ".db-wal", ".duckdb", ".lock",
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2",
        ".map", ".min.js",
    })
    _NOISE_PREFIXES = (
        ".vscode/", ".git/", "node_modules/", "__pycache__/",
        "dist/", "build/", ".cache/",
    )

    def _is_noise(self, fname: str) -> bool:
        if any(fname.startswith(p) for p in self._NOISE_PREFIXES):
            return True
        _, ext = os.path.splitext(fname.lower())
        return ext in self._NOISE_SUFFIXES

    def workspace_summary(self, opts: dict) -> dict:
        """Fast workspace-level git overview: hot source files, authors, recent commits."""
        git_root = _find_git_root(self._root)
        if not git_root:
            return {"available": False, "reason": "not a git repository"}

        max_commits = 100

        branch = _run(["git", "branch", "--show-current"], cwd=git_root).strip()

        # One call: structured commit header + touched files.
        # Sentinel prefix "C>" is safe in list-based Popen (no shell interpretation).
        raw = _run(
            [
                "git", "log",
                f"--max-count={max_commits}",
                "--format=C>%h|%ad|%an|%s",
                "--name-only",
                "--date=short",
            ],
            cwd=git_root,
        )

        recent_commits: list[dict] = []
        file_touches: dict[str, int] = {}
        author_counts: dict[str, int] = {}

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("C>"):
                meta = stripped[2:].split("|", 3)
                commit = {
                    "commit": meta[0] if len(meta) > 0 else "",
                    "date":   meta[1] if len(meta) > 1 else "",
                    "author": meta[2] if len(meta) > 2 else "",
                    "message": meta[3] if len(meta) > 3 else "",
                }
                recent_commits.append(commit)
                if commit["author"]:
                    author_counts[commit["author"]] = author_counts.get(commit["author"], 0) + 1
            elif not self._is_noise(stripped):
                file_touches[stripped] = file_touches.get(stripped, 0) + 1

        top_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Group hot files by touch count — avoids repeating the key for every file
        grouped: dict[int, list[str]] = {}
        for f, c in sorted(file_touches.items(), key=lambda x: x[1], reverse=True)[:15]:
            grouped.setdefault(c, []).append(f)

        return {
            "branch": branch or "unknown",
            "commits_sampled": len(recent_commits),
            "recent_commits": [f"{c['commit']} | {c['date']} | {c['message']}" for c in recent_commits[:10]],
            "hot_files": {str(k): v for k, v in sorted(grouped.items(), reverse=True)},
            "top_authors": [f"{a} ({c})" for a, c in top_authors],
            "_tip": "recall(query='<file>') → commit-by-commit diffs for that file",
        }
