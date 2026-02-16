# ShadowGraph

> **Code is a Graph of States. Why should documentation be anything else?**

## The Core Insight

When you compile code, you get a **directed acyclic graph (DAG)** of states and transitions. Each function is a node. Each call is an edge. The compiled binary *is* the graph.

But when you try to understand the code—when you ask "what breaks if I change this?"—you're forced to read **static text comments** that:

- **Bloat the context window** (degrading AI agent reasoning)
- **Drift out of sync** (orphaned after refactoring)
- **Don't express relationships** (no edges, no causality)
- **Can't be queried** (you have to read them manually)

**ShadowGraph solves this:** It creates a **semantic knowledge graph** that mirrors the code graph—not as static comments, but as queryable, versioned, agent-accessible connections.

## The Problem: Static Comments Destroy Context

### Why Comments Are Broken for AI Agents

An AI agent trying to debug or modify code faces a **context trilemma**:

```
Option 1: Read all comments
→ Context bloat (10,000+ tokens)
→ LLM loses precision ("Lost in the Middle")
→ Hallucinations spike
→ Cost: $0.05 per query

Option 2: Read only relevant files
→ Miss critical constraints (in unrelated files)
→ Break invariants unknowingly
→ Silent failures in production

Option 3: Ignore comments entirely
→ Miss intent entirely
→ Reinvent decisions already made
→ Waste tokens re-discovering constraints
```

**None of these options work.** Why? Because comments are **static text**, not **structured relationships**.

### The Real Problem: Comments Don't Express Graphs

Code has structure:

```
Function A → calls → Function B → depends on → Database X
Function B → validates → Constraint Y (idempotency required)
Constraint Y → implemented via → Redis cache with 24h TTL
```

But comments express this as:

```
// See Function B for logic
// TODO: verify idempotency
// NOTE: Redis cache TTL is 24 hours (see config)
```

**A comment is just text.** It can't express:

- ❌ "Don't change this without also changing that"
- ❌ "This breaks if the dependency drifts"
- ❌ "This was added to satisfy constraint X"
- ❌ "This is O(n^2) for dataset < 100 items"

An AI agent reading this text has to **infer** the relationships. It guesses. It hallucinates.

## The Solution: A Semantic Knowledge Graph

ShadowGraph creates a **queryable graph** where code's intent is explicit as edges and nodes—not implicit as comments.

```python
# Code (clean, no bloat):
def charge(amount):
    try:
        return stripe.charge(amount)
    except StripeError:
        return None

# Graph (in ShadowGraph, not in code):
{
  "node": "charge()",
  "type": "function",
  "thoughts": [
    "Swallow Stripe errors due to idempotency keys",
    "If retry hits 'already charged' error, we ignore 409 Conflict"
  ],
  "edges": {
    "depends_on": ["stripe.charge()", "idempotency_key_handler()"],
    "required_by": ["CONSTRAINT: Payment must be idempotent"],
    "called_by": ["OrderService.place_order()"],
    "breaks_if_changed": [
      "stripe.charge() return type",
      "redis cache TTL (currently 24h)"
    ]
  },
  "warnings": {
    "stale_dependency": "idempotency_key_handler() changed 3 days ago"
  }
}
```

**Now an AI agent can query:**

- ✅ "What are the thoughts on this function?"
- ✅ "What breaks if I change this?"
- ✅ "What constraints apply here?"
- ✅ "What changed in my dependencies recently?"
- ✅ "What calls this function?"

**Result:** 200 tokens of focused, structured context instead of 10,000 tokens of bloated text.

## Why This Matters for AI Agents

### The Context Window Problem

When an AI agent sees:

```
def charge(amount):
    """Process payment."""
    # We swallow errors because of idempotency
    # Don't change without consulting payment team
    # Also see: AuthService (line 45)
    # Also see: CurrencyConverter (line 120)
    # Also see: fraud detection (line 200)
    # NOTE: Redis cache used here
    # NOTE: Stripe API v2 endpoint
    # See config.py for stripe key
    try:
        return stripe.charge(amount)
    except StripeError:
        # Intentional (see comments above)
        return None
```

The agent thinks:

- "OK, so I need to read 5 other files"
- "I need to see config.py"
- "Maybe I need to check Stripe API docs"
- "I should look at the payment team's Slack"

So it pulls in 2,000 lines across 8 files. The context window explodes. The LLM's reasoning degrades. **Hallucinations increase.**

### With ShadowGraph

Agent sees a **graph query result:**

```json
{
  "charge()": {
    "thoughts": [
      "Swallow errors due to idempotency keys (Stripe returns 409)",
      "If charge fails after retry, retry hits 'already charged'"
    ],
    "depends_on": [
      {"symbol": "stripe.charge()", "status": "valid"},
      {"symbol": "idempotency_key()", "status": "stale", "changed": "3d ago"}
    ],
    "constraints": [
      {"rule": "Must be idempotent", "severity": "critical"}
    ]
  }
}
```

The agent has **20 tokens of focused context**. It knows:

- ✅ The intent (why this code exists)
- ✅ The constraints (what it must do)
- ✅ The risks (what changed recently, what breaks it)
- ✅ The topology (what depends on it, what it depends on)

**No hallucinations. Perfect clarity. 50x cheaper.**

## How ShadowGraph Saves Intent

### 1. **Agents Record Thoughts**

When an AI agent modifies code, it doesn't just edit—it records **why**:

```
Agent: "I'm updating the Stripe API call to v3"
→ ShadowGraph records:
   - THOUGHT: "Migrated to Stripe API v3. Returns different error codes."
   - EDGE: Updated charge() → depends_on → stripe.charge_v3()
   - STALE: Marked idempotency_key() as STALE (might need adjustment)
```

### 2. **Thoughts Anchor to Symbols, Not Lines**

Comments die when code is refactored. Thoughts stay:

```python
# Before refactoring:
def charge(amount):
    # Line 42: Swallow Stripe errors due to idempotency
    try:
        stripe.charge(amount)
    except StripeError:
        return None

# After refactoring (added retry logic):
def charge_with_retry(amount, max_retries=3):
    for attempt in range(max_retries):
        try:
            stripe.charge(amount)
        except StripeError:
            if attempt < max_retries - 1:
                wait(attempt)
            else:
                return None

# Old comment: LOST (was at line 42, now code is different)
# ShadowGraph thought: ATTACHED (anchored to charge() function signature)
```

### 3. **Agents Know What Will Break**

Before making a change, an agent can query:

```python
query_blast_radius("charge", depth=2)

Returns:
{
  "what_depends_on_me": [
    "OrderService.place_order()",
    "webhook.handle_charge_retry()"
  ],
  "what_i_depend_on": [
    "stripe.charge() [STALE: changed 3 days ago]",
    "idempotency_key() [valid]",
    "CONSTRAINT: Payment must be idempotent"
  ],
  "if_i_change": [
    "⚠️ OrderService might break (verify idempotency still holds)",
    "⚠️ Webhook retry logic depends on error behavior"
  ]
}
```

Agent sees the risks before making changes. **No silent failures.**

### 4. **Knowledge Persists Across Sessions**

Every thought, constraint, and decision is **saved in a graph** (not as comments):

```
Session 1 (Day 1):
- Agent: "Added caching to reduce DB calls"
- Records: THOUGHT linked to function

Session 2 (Day 7):
- Agent: "Seeing stale data. Need to invalidate cache."
- Queries: "Show me all thoughts about this function"
- Sees: "Cache added 7 days ago. TTL is 24h."
- Diagnosis: "Cache invalidation issue" (not re-discovered from scratch)
```

## What This Enables

### For Agents

- **Structured reasoning:** Query the graph, don't read text
- **Constraint awareness:** Know rules before you break them
- **Debugging precision:** See dependencies and stale edges
- **Long-term memory:** Thoughts persist across sessions

### For Developers

- **Zero comment bloat:** Code stays clean and readable
- **Intent preservation:** Thoughts validate against code drift
- **Team knowledge:** Graph is Git-tracked; teammates see your reasoning
- **Debugging speed:** Agents can pinpoint root causes in minutes, not hours

### For Companies

- **Faster onboarding:** New hires query the graph instead of reading 100 files
- **Fewer bugs:** Agents understand constraints before modifying code
- **Lower AI costs:** 50x token reduction = 50x cheaper per query
- **Preserved intent:** Code + reasoning evolve together

## The Fundamental Difference

| Traditional                                             | ShadowGraph                                                   |
| ------------------------------------------------------- | ------------------------------------------------------------- |
| **Comments:** Static text, bound to lines         | **Graph:** Queryable nodes and edges                    |
| **Structure:** Narrative prose                    | **Structure:** Causal relationships                     |
| **For agents:** Context bloat, hallucinations     | **For agents:** Precise context, 50x fewer tokens       |
| **Maintenance:** Comments drift after refactoring | **Maintenance:** Thoughts validated by code drift       |
| **Debugging:** "Read this file and figure it out" | **Debugging:** "Query the graph, here are the answers"  |
| **Expressiveness:** "See line 45 for more info"   | **Expressiveness:** "Function X breaks if you change Y" |

## How It Works

### 1. Index Your Code

```bash
ShadowGraph: Index Current File
```

Extracts functions/classes via tree-sitter AST hashing.

### 2. Agents Record Thoughts

```python
# While modifying code:
agent_records_thought(
    symbol="charge()",
    thought="Updated to Stripe API v3. Error codes now different.",
    context="Idempotency still required. Cache TTL still 24h."
)
```

### 3. Query the Graph for Debugging

```python
query_blast_radius("charge", depth=2)
# Returns: All connected nodes, edges, thoughts, constraints, warnings
```

### 4. Share with Team

```bash
git add .shadow/graph.jsonl
git commit -m "docs: record architectural decisions"
git push
```

Teammates pull and instantly see all context.

## The Vision

**Code is a graph. Documentation should be a graph. Agents should query it.**

Instead of static comments that decay, ShadowGraph creates a **semantic knowledge layer** that:

- Mirrors the code graph (nodes = functions, edges = calls + constraints)
- Expresses causality ("this breaks if that changes")
- Saves agent reasoning (what it learned, what it feared)
- Stays in sync (validation against code drift)
- Is queryable (structured data, not prose)

**Result:** Agents work with precision, not guessing. Debugging takes minutes, not hours. Code + intent evolve together.

---

**The future of code isn't comments. It's graphs.**
