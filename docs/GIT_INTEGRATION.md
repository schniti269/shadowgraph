# Git Integration: Hive Mind Collaboration

## The Problem: Local Knowledge is Lost on Pull

**Without ShadowGraph Git Integration:**
```
Developer A                           Developer B (Pulls Later)
├─ Adds thought to AuthService:       ├─ git pull origin main
│  "We use sessions not tokens        ├─ Sees updated code
│   because legacy monolith..."       ├─ No context about WHY
├─ Commits code                       ├─ Re-discovers the same issue:
└─ Pushes                             │  "Why use sessions?"
                                      └─ Wastes 2 hours reading git history
```

**With ShadowGraph Git Integration (Hive Mind):**
```
Developer A                           Developer B (Pulls Later)
├─ Adds thought via ShadowGraph       ├─ git pull origin main
├─ Commits .shadow/graph.jsonl        ├─ ShadowGraph auto-loads .shadow/graph.jsonl
├─ Pushes                             ├─ Sees A's thought instantly:
└─ Done                               │  "Sessions not tokens because monolith..."
                                      └─ Understands architecture in seconds
```

The difference: **Tribal knowledge becomes repo knowledge.**

## How It Works: The Three-Layer Architecture

### Layer 1: Local Database (Not Committed)
```
.vscode/shadow.db          ← SQLite database
.vscode/shadow.db-wal      ← Write-ahead log
.vscode/shadow.db-shm      ← Shared memory file
```

- **Location**: `.vscode/shadow.db` (in `.gitignore`)
- **Purpose**: Live database for reads/writes
- **Regenerated**: From `.shadow/graph.jsonl` on every pull
- **Lifetime**: Session-scoped, not persisted across machines

### Layer 2: Shared Graph (Committed to Git)
```
.shadow/graph.jsonl        ← Serialized graph
.shadow/.gitkeep           ← Keep folder in git
.shadow/.gitignore         ← Ignore *.db files
```

- **Location**: `.shadow/graph.jsonl` (tracked by git)
- **Format**: JSONL (one node/edge per line)
- **Purpose**: Version-controlled snapshot of thoughts + structure
- **Updated**: When you commit code + thoughts
- **Lifetime**: Persistent, shared across team

### Layer 3: Conflict Resolution (Automatic)
- **Strategy**: Last-write-wins (LWW) based on timestamps
- **Sync IDs**: Hash of node ID + content for change tracking
- **Merge conflicts**: Detected and reported, not auto-resolved if critical

## The Workflow

### 1. Developer A: Adding Thoughts

```bash
# Developer A edits AuthService
$ cat src/auth.ts
export class AuthService {
  // ...implementation

# Run ShadowGraph command
$ Command Palette → ShadowGraph: Add Thought

# Add thought (in VS Code UI)
💭 Thought: "We use session tokens (not JWT) because the legacy monolith
   can't validate JWT signatures. Refactoring to JWT requires updating
   the entire auth service. Tracked in EPIC-123."

# Local effect: Thought stored in .vscode/shadow.db
# Shadow graph now has: AuthService → HAS_THOUGHT → [thought with timestamp]

# Developer A commits code
$ git add src/auth.ts .shadow/graph.jsonl
$ git commit -m "docs: explain session token architecture via ShadowGraph"

# Behind the scenes:
# 1. Extension calls serializer.serialize_to_jsonl()
# 2. Python exports all nodes/edges to .shadow/graph.jsonl
# 3. Each node has sync_id = hash(id + content) for conflict detection
# 4. git tracks the JSONL changes

$ git push origin feature/auth-refactor
```

### 2. Developer B: Pulling Code

```bash
# Developer B pulls the repository
$ git pull origin feature/auth-refactor

# Git fetches:
# - Updated src/auth.ts (code changes)
# - Updated .shadow/graph.jsonl (thoughts + structure)
# - (NOT .vscode/shadow.db — that's in .gitignore)

# VS Code Extension Auto-Acts:
# 1. Detects .shadow/graph.jsonl changed
# 2. Calls deserializer.deserialize_from_jsonl()
# 3. Python reads JSONL and hydrates .vscode/shadow.db
# 4. Merge strategy: LWW (timestamps)
# 5. Extension reloads UI

# Result: Dev B sees A's thought instantly!
```

### 3. Developer B: Working with Inherited Context

```typescript
// Dev B opens AuthService
class AuthService {
  // CodeLens shows: 🧠 1 thought

// Click thought or run Command Palette → Show Thoughts
// Sees:
💭 "We use session tokens (not JWT) because the legacy monolith
   can't validate JWT signatures. Refactoring to JWT requires updating
   the entire auth service. Tracked in EPIC-123."
   — Added by Developer A, 2026-02-14

// Dev B understands the constraint and context
// Can now refactor confidently with full awareness
```

### 4. Handling Conflicts (Manual)

If both developers edit the same symbol's thought:

```bash
$ git pull
# CONFLICT in .shadow/graph.jsonl

# Git marks the conflict:
<<<<<<< HEAD
{"id":"thought:abc","content":"Our version","created_at":"2026-02-14T10:00:00Z"}
=======
{"id":"thought:abc","content":"Their version","created_at":"2026-02-14T09:00:00Z"}
>>>>>>>

# ShadowGraph UI prompts:
"Conflict detected in thought for AuthService.
 Your version: <timestamp A>
 Their version: <timestamp B>
 Auto-resolve using LWW: <newer version>"

# Choose:
# ✅ Accept newer (based on timestamp)
# ✅ Merge manually (edit both thoughts into one)
# ✅ Keep both (create new node for alternative view)

$ git add .shadow/graph.jsonl
$ git commit -m "resolve: merge AuthService thoughts"
$ git push
```

## JSONL Format

**Example .shadow/graph.jsonl:**

```json
{"id":"code:auth.ts:class:AuthService","type":"CODE_BLOCK","content":"export class AuthService...","created_at":"2026-02-10T08:00:00Z","sync_id":"abc123def456"}
{"id":"thought:xyz789","type":"THOUGHT","content":"We use session tokens...","created_at":"2026-02-14T10:30:00Z","sync_id":"xyz789uvw012"}
{"source_id":"code:auth.ts:class:AuthService","target_id":"thought:xyz789","relation":"HAS_THOUGHT","sync_id":"rel123456789"}
{"id":"code:payment.ts:function:charge","type":"CODE_BLOCK","content":"export async function charge...","created_at":"2026-02-11T14:15:00Z","sync_id":"pqr345stu678"}
{"source_id":"code:payment.ts:function:charge","target_id":"code:auth.ts:class:AuthService","relation":"DEPENDS_ON","sync_id":"rel987654321"}
```

**Key properties:**
- **One object per line** (newline-delimited JSON)
- **sync_id**: Hash of `id + content` for change tracking
- **created_at**: ISO 8601 UTC timestamp
- **type**: NODE types (CODE_BLOCK, THOUGHT, CONSTRAINT) OR edge metadata
- **relation**: HAS_THOUGHT, DEPENDS_ON, REQUIRED_BY, IMPACTS

**Benefits of JSONL format:**
- **Diff-friendly**: Each node/edge is one line
- **Mergeable**: Conflict markers on individual objects, not across the file
- **Streamable**: Process one node at a time (for large graphs)
- **Version control friendly**: Git understands line-based changes

## Gitignore Configuration

Create `.shadow/.gitignore`:

```
# Ignore local database files (not shared across team)
*.db
*.db-wal
*.db-shm

# Track the serialized graph
!graph.jsonl
```

Create root `.gitignore` entry:

```
# ShadowGraph local database
.vscode/shadow.db
.vscode/shadow.db-*

# Python cache
__pycache__/
*.pyc
.pytest_cache/
```

## Merge Strategy: Last-Write-Wins (LWW)

When two developers edit the same symbol's thought:

```
Developer A (2026-02-14 10:30 UTC)    Developer B (2026-02-14 10:45 UTC)
├─ Edits AuthService thought          ├─ Pulls from main
├─ created_at: 2026-02-14T10:30Z      ├─ Sees Developer A's thought
├─ content: "Session tokens..."       ├─ Edits the SAME thought
└─ Pushes                             ├─ created_at: 2026-02-14T10:45Z
                                      ├─ content: "Session tokens..."
                                      └─ Pushes (conflict!)

Merge Resolution:
- Both have same thought id
- Timestamps differ: 10:45 > 10:30
- Winner: Developer B (later edit)
- Loser's content: Available in git history
```

**Why LWW?**
- Simple, deterministic (no user interaction on every pull)
- Based on timestamps (no clock skew issues if you use UTC)
- Team can review losers in git history if needed
- For critical conflicts, team uses comments in PR to explain

**Alternative: Ask User**
If you prefer explicit merges:
```typescript
// In git-integration.ts
if (incomingSync > localSync) {
  // Auto-accept newer version
  accept(incomingVersion);
} else {
  // Prompt user for decision
  vscode.window.showInformationMessage(
    `Conflict in ${symbol}: Keep local or incoming?`,
    'Keep Local', 'Accept Incoming', 'Review Both'
  );
}
```

## Workflow Examples

### Example 1: Onboarding New Developer

```bash
# Day 1: New developer joins
$ git clone https://github.com/company/app.git
$ cd app
$ code .

# VS Code opens
# Extension activation:
# 1. Creates .vscode/shadow.db
# 2. Reads .shadow/graph.jsonl
# 3. Hydrates database with existing thoughts
# 4. Shows CodeLens with thought counts

# Developer opens PaymentProcessor.ts
# Sees CodeLens: 🧠 3 thoughts
# Clicks thought: "⚠️ Stripe error swallowing due to idempotency keys"
# Instant context! Understands constraints before reading code.
```

### Example 2: Collaborative Refactoring

```bash
# Team is refactoring AuthService
# Developer A: "I'm updating session storage to Redis"
$ git checkout -b feature/redis-sessions

# Modifies AuthService
$ Command Palette → ShadowGraph: Add Thought
💭 "Migrated from in-memory sessions to Redis.
   Allows horizontal scaling. Tested with 1000 concurrent sessions.
   See load test results in EPIC-456."

$ git add . && git commit -m "feat: Redis sessions"
$ git push

# Developer B: "I need to understand this before deploying"
$ git pull origin feature/redis-sessions

# Sees the thought immediately
# Can review change with full context
# Opens PR with confidence: "I understand the refactoring"
```

### Example 3: Constraint Enforcement

```bash
# Constraint in graph: "Payments must be idempotent"
# Team maintains this as a CONSTRAINT node

# Developer C modifies PaymentProcessor (violates constraint)
$ git add . && git commit -m "temp: debug payment flow"
$ git push

# CI/CD runs:
$ graph-check .vscode/shadow.db src/ --fail-on critical

# Output:
❌ CONSTRAINT VIOLATION: "Payments must be idempotent"
   Symbol: code:payment.ts:function:charge
   Severity: critical
   Fix: Add idempotency key to Stripe API call
   Context: See CONSTRAINT node for rationale

# Developer C sees the constraint, checks the thought
# "Ah, I need to add idempotency key. Here's why..."
# Fixes code, CI passes
```

## Serialization & Deserialization

### When Serialization Happens

1. **Automatic**: When you commit code via `git add . && git commit`
   - Extension calls `serializer.serialize_to_jsonl()` on every save

2. **Manual**: Run `Command Palette → ShadowGraph: Export to Git`
   - Explicitly serialize current database to `.shadow/graph.jsonl`

3. **CLI**: `tools/graph-check.py serialize <db_path> <output.jsonl>`
   - For CI/CD or batch operations

### When Deserialization Happens

1. **On Pull**: When `.shadow/graph.jsonl` changes
   - File watcher detects change
   - Extension calls `deserializer.deserialize_from_jsonl()`
   - Database reloaded with merged graph

2. **On Open**: When workspace opens
   - Extension checks if `.shadow/graph.jsonl` exists
   - If yes: deserialize to populate `.vscode/shadow.db`
   - If no: start with empty database

3. **Conflict Resolution**: When merge conflicts detected
   - User chooses LWW or manual merge
   - Then deserialize the resolved JSONL

## Handling Network Issues

**Scenario: Developer pulls before all thoughts are serialized**

```bash
# Developer A is working
$ Command Palette → Add Thought
# (Thought created in .vscode/shadow.db)
# (NOT YET serialized to .shadow/graph.jsonl)

# Developer A is about to commit, but...
# Network goes down, close laptop

# Developer B pulls in the meantime
$ git pull
# Gets old .shadow/graph.jsonl (without A's thought)

# When A comes back online:
$ git commit -m "docs: add thoughts" -a
# Extension serializes NOW (includes A's thought)

$ git push
# B's pull request now gets the new JSONL on their next pull
```

**Solution**: Serialize on every significant change:
- On `add_thought()`
- On `edit_code_with_thought()`
- On `add_constraint()`
- Before each commit (via git hook)

## GitHub Integration

### GitHub Actions Workflow

```yaml
name: ShadowGraph Integrity

on: [pull_request, push]

jobs:
  serialize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      # Verify graph.jsonl is valid JSON lines
      - name: Validate JSONL format
        run: |
          while IFS= read -r line; do
            echo "$line" | jq empty || exit 1
          done < .shadow/graph.jsonl

      # Check for merge conflicts
      - name: Check for merge markers
        run: |
          if grep -q '^<<<<<<< HEAD' .shadow/graph.jsonl; then
            echo "❌ Unresolved conflict in graph.jsonl"
            exit 1
          fi

      # Verify constraints
      - name: Validate constraints
        run: |
          python tools/graph-check.py \
            .vscode/shadow.db src/ \
            --fail-on critical
```

## Best Practices

1. **Serialize regularly**: Don't let `.vscode/shadow.db` and `.shadow/graph.jsonl` drift too far
2. **Write clear thoughts**: Team members depend on your context
3. **Review JSONL in PRs**: Ensure conflicts are resolved correctly
4. **Use timestamps**: Always include `created_at` for LWW resolution
5. **Commit graph with code**: When you change code, commit thoughts too
6. **Don't hand-edit JSONL**: Use ShadowGraph UI, not a text editor

## Troubleshooting

### "graph.jsonl is corrupted"

```bash
# Check for invalid JSON
$ while IFS= read -r line; do
    echo "$line" | jq empty
  done < .shadow/graph.jsonl

# Fix: Regenerate from database
$ Command Palette → ShadowGraph: Export to Git
```

### "After pull, my thoughts disappeared"

```bash
# Check if .shadow/graph.jsonl has your thoughts
$ git log -p .shadow/graph.jsonl | grep "your thought text"

# If present in history but missing now:
# LWW conflict resolution removed it (older timestamp)
# Solution: Add thought again with new timestamp
$ Command Palette → Add Thought
```

### "Merge conflicts in graph.jsonl"

```bash
# Option 1: Auto-resolve using LWW
$ git checkout --ours .shadow/graph.jsonl  # Keep local
# OR
$ git checkout --theirs .shadow/graph.jsonl  # Accept incoming

# Option 2: Manual merge
# Edit .shadow/graph.jsonl, remove conflict markers
# Keep both thoughts if they're not duplicates

$ git add .shadow/graph.jsonl
$ git commit -m "resolve: merge thoughts from feature branch"
```

## Future: Real-time Collaboration

Phase 4 will add:
- WebSocket sync for live multi-user editing
- Operational transformation (OT) for conflict-free merging
- Real-time presence indicators
- Live cursors showing who's editing what

For now, git provides sufficient concurrency with LWW merge strategy.

---

**See Also:**
- [README.md](../README.md) - Quick start
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical design
- [BLAST_RADIUS.md](./BLAST_RADIUS.md) - Debugging guide

**Last Updated**: 2026-02-15 (Phase 3)
