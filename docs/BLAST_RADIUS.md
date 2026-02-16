# Blast Radius Analysis: Dependency-Aware Debugging

## The Problem: "What Breaks if I Change This?"

Traditional debugging is **local**:
- You see an error in `PaymentProcessor.charge()`
- You read the stack trace
- You read the function line-by-line
- You hope you found the root cause
- You hope your fix doesn't break something 10 files away

Modern debugging needs to be **graphical**:
- What calls `PaymentProcessor.charge()`? (impact analysis)
- What does `PaymentProcessor` call? (dependency analysis)
- What changed recently in my dependencies? (temporal analysis)
- What context did my team add about these dependencies? (intent analysis)

**Blast Radius Analysis** answers all four questions at once.

## Core Concept: The Semantic Neighborhood

Every symbol exists in a web:

```
                      ┌─ LoginUI
                      │  (imports)
                      │
                      ↓
    ┌─────────────────────────────────────┐
    │    PaymentProcessor.charge()        │
    │    💭 "Swallow Stripe errors to..."│
    └─────────────────────────────────────┘
          ↑                      ↓
         /│\                    /│\
        / │ \                  / │ \
       /  │  \                /  │  \
      /   │   \              /   │   \
  AuthService │  CurrencyConverter   StripeSDK
              │       🚨 STALE
              │       (Changed 2h ago)
              │
         OrderService
```

**Outgoing edges** (what I depend on):
- `AuthService` — check tokens before charging
- `CurrencyConverter` — exchange rates for multi-currency
- `StripeSDK` — process payment

**Incoming edges** (who depends on me):
- `OrderService` — calls `charge()` when order placed
- `LoginUI` — indirect: through OrderService

**Attached thoughts**:
- "Swallow Stripe errors due to idempotency keys"
- "CurrencyConverter API changed 2 hours ago"

**Stale flags**:
- `CurrencyConverter` is STALE — code changed since last thought

When an error hits `PaymentProcessor`, an AI agent can:
1. Call `query_blast_radius("PaymentProcessor", depth=2)`
2. Get the full semantic neighborhood
3. See `CurrencyConverter` is STALE + see attached thought about API change
4. Diagnose: "Return type changed from float to string, but PaymentProcessor expects float"
5. Fix with 95% less guesswork

## How to Use Blast Radius

### Via Command Palette

1. Open any code file
2. Click on a function/class name
3. Run: `Command Palette (Cmd+Shift+P) → ShadowGraph: Analyze Blast Radius`
4. A TreeView appears showing:
   - **Origin node**: The symbol you clicked
   - **Dependencies** (outgoing): What it calls
   - **Dependents** (incoming): Who calls it
   - **Context**: Attached thoughts + stale flags

### Via Copilot Agent

```
User: "I'm getting a TypeError in PaymentProcessor. Help me understand what could break."

Agent: I'll analyze the blast radius of PaymentProcessor to understand its dependencies.

[Agent calls: query_blast_radius("PaymentProcessor", depth=2)]

Agent response:
✅ PaymentProcessor.charge() is an origin node with 3 dependencies:
   1. AuthService (VALID, thought: "Check OAuth token")
   2. CurrencyConverter (🚨 STALE, thought: "Returns string not float since 2h ago")
   3. StripeSDK (VALID, thought: "Error swallowing due to idempotency")

📊 Impact: 2 dependents (OrderService, LoginUI [indirect])

🔍 Root cause found: CurrencyConverter returns string, but your code expects float.
   This change happened 2 hours ago. The STALE flag confirmed the mismatch.

💡 Fix: Convert CurrencyConverter result to float before using in charge calculation.
```

### Via CLI (Future)

```bash
# Show blast radius as JSON
shadowgraph blast-radius PaymentProcessor --depth=2 --format=json

# Show as Mermaid diagram
shadowgraph blast-radius PaymentProcessor --depth=2 --format=mermaid

# Filter by stale symbols
shadowgraph blast-radius PaymentProcessor --depth=2 --stale-only
```

## MCP Tool: `query_blast_radius()`

**Signature:**
```python
def query_blast_radius(symbol_name: str, depth: int = 2) -> str:
    """
    Retrieve the semantic neighborhood of a symbol.

    Args:
        symbol_name: e.g., "function:charge" or "class:PaymentProcessor"
        depth: How many hops to follow (1=direct, 2=transitive)

    Returns:
        JSON with nodes, edges, thoughts, stale flags
    """
```

**Example Request (Copilot agent):**
```json
{
  "tool": "query_blast_radius",
  "arguments": {
    "symbol_name": "function:charge",
    "depth": 2
  }
}
```

**Example Response:**
```json
{
  "origin": {
    "symbol": "function:charge",
    "file": "payment.ts",
    "type": "CODE_BLOCK",
    "thoughts": [
      {
        "id": "thought:xyz123",
        "text": "Swallow Stripe errors to prevent retries on idempotent keys",
        "created_at": "2026-02-14T10:30:00Z"
      }
    ]
  },

  "neighborhood": {
    "level_1": {
      "dependencies_outgoing": [
        {
          "symbol": "function:checkToken",
          "file": "auth.ts",
          "stale": false,
          "anchor_status": "VALID",
          "thoughts": [
            {
              "text": "OAuth 2.0 with refresh token rotation",
              "created_at": "2026-02-10..."
            }
          ]
        },
        {
          "symbol": "function:convertCurrency",
          "file": "converter.ts",
          "stale": true,
          "anchor_status": "STALE",
          "changed": "2026-02-13T08:15:00Z",
          "thoughts": [
            {
              "text": "Updated to Stripe Currency API v2. Returns string not float!",
              "created_at": "2026-02-13T08:15:00Z"
            }
          ]
        },
        {
          "symbol": "function:processPayment",
          "file": "stripe-sdk.ts",
          "stale": false,
          "thoughts": []
        }
      ],

      "dependents_incoming": [
        {
          "symbol": "function:placeOrder",
          "file": "order.ts",
          "stale": false,
          "relation": "DEPENDS_ON (calls)"
        }
      ]
    },

    "level_2": {
      "transitive_dependencies": [
        {
          "symbol": "class:StripeAPIClient",
          "file": "stripe-sdk.ts",
          "stale": false,
          "reachable_via": ["processPayment → StripeAPIClient"]
        }
      ],

      "transitive_dependents": [
        {
          "symbol": "function:checkoutUI",
          "file": "ui.ts",
          "stale": false,
          "reachable_via": ["checkoutUI → placeOrder → charge"]
        }
      ]
    }
  },

  "summary": {
    "total_dependencies": 3,
    "total_dependents": 2,
    "stale_count": 1,
    "critical_stale": [
      {
        "symbol": "function:convertCurrency",
        "reason": "Return type changed. Code expects float, now returns string."
      }
    ]
  }
}
```

## Understanding the Output

### Stale Flags 🚨

A symbol is **STALE** when:
- Its code changed since the last indexed anchor
- AST hash no longer matches stored hash
- Could indicate: refactoring, bug fix, API change, breaking change

**How to read a STALE flag:**
```
✅ AuthService (VALID)         → Code unchanged since last thought
🚨 CurrencyConverter (STALE)   → Code changed! See attached thought
                                 (should explain the change)
```

### Thought Context 💭

Every node can have attached thoughts explaining WHY:
- Why this function exists
- Why it calls these dependencies
- What changed recently
- Known issues or trade-offs

When debugging, **always read the thoughts** on stale dependencies.

### Relation Types

**Outgoing (dependencies):**
- `DEPENDS_ON (import)` — Import statement, module loading
- `DEPENDS_ON (calls)` — Function call
- `DEPENDS_ON (inherits)` — Class inheritance

**Incoming (dependents):**
- `DEPENDS_ON (import)` — Someone imports this
- `DEPENDS_ON (calls)` — Someone calls this
- `IMPACTS` — Inverse of DEPENDS_ON

## Real-World Debugging Scenario

### Scenario: "503 Service Unavailable" in PaymentProcessor

**Error Log:**
```
ERROR: TypeError in PaymentProcessor.charge()
  at line 45: amount * exchange_rate
  TypeError: unsupported operand type(s) for *: 'float' and 'str'
```

**Traditional Debugging:**
1. Open `payment.ts`
2. Read `charge()` function (50 lines)
3. Find the error at line 45: `amount * exchange_rate`
4. Check what `convertCurrency()` returns
5. Open `converter.ts` (200 lines)
6. Read entire file, check return type
7. Find recent commit: "Updated to Stripe v2 API"
8. Read commit message, understand API changed return type
9. Fix code to convert string to float
10. Total time: 30+ minutes

**Blast Radius Debugging:**
1. Click on `charge()` in editor
2. Run: `ShadowGraph: Analyze Blast Radius`
3. See dependency: `convertCurrency` is STALE (red icon)
4. Hover over: Thought says "Updated to Stripe Currency API v2. Returns string not float!"
5. Click "Show Code" → See updated function
6. Fix: Add `float()` conversion
7. Total time: 2 minutes

**The difference**: With Blast Radius, you don't read 250 lines of code. You read the 2-line thought that was specifically added to explain the change.

## Best Practices

### When Adding Thoughts, Be Specific

❌ **Bad:**
```
"Updated this function"
```

✅ **Good:**
```
"Updated to Stripe Currency API v2 (v1 deprecated 2026-02-01).
Returns string price instead of float. Breaking change!
Converted to float before multiplication. See line 45."
```

### When Dependencies Change, Update Thoughts

If you refactor `CurrencyConverter` return type:
1. Make code change
2. Run `index_file()` to update AST hash
3. Edit the existing thought to document the change
4. Example: "Returns string (was float in v1). Handles decimal precision better."

### Use Depth Strategically

- **depth=1**: Direct dependencies only (fast, focused)
- **depth=2**: Transitive dependencies (most useful, balanced)
- **depth=3+**: Can be slow, use only when investigating widespread impact

### Check Stale Flags First

When debugging:
1. Call `query_blast_radius(symbol, depth=2)`
2. **Filter for STALE symbols first**
3. Read their attached thoughts
4. 80% of bugs are in recently-changed dependencies

## Integration with Copilot

### Agent Workflow Pattern

```python
# Agent analyzing an error
1. Extract error symbol from stack trace
2. Call query_blast_radius(error_symbol, depth=2)
3. Filter response by stale=true
4. For each stale dependency, call get_context() to see code
5. Correlate timestamp of stale anchor with error time
6. Propose fix based on thought context
```

### Copilot Can Directly Use the Response

The MCP tool response is structured JSON that Copilot can:
- Render as a tree diagram in chat
- Filter by stale flags
- Highlight critical dependencies
- Link to code locations
- Propose fixes based on thought context

## Constraints + Blast Radius

**Bonus**: Combine blast radius with constraints.

Example:
```
Constraint: "Payment processing must be idempotent"
Applied to: PaymentProcessor.charge()

Error: "Duplicate charge detected"

Agent workflow:
1. query_blast_radius("charge") → see all dependencies
2. validate_constraints("payment.ts") → see "idempotency" constraint
3. Check if any dependency violates idempotency
4. Find: StripeSDK.processPayment() → no retry logic
5. Propose: Add idempotency key to Stripe request
```

## Performance Considerations

### Recursive Query Limits

- Default depth: 2 (sufficient for 95% of debugging)
- Max recommended: 3 (prevents quadratic blowup)
- Large graphs (1000+ nodes): Use depth=1, then drill down

### Caching

Blast radius results are cached for 5 minutes to avoid redundant queries.

### Pagination (Future)

For symbols with 100+ dependents, results will paginate (coming in Phase 4).

## Summary

**Blast Radius Analysis** turns dependency debugging from "read 250 lines of code" into "read 1 thought that explains the change."

Key benefits:
- 95% reduction in context noise
- AI agents diagnose errors in seconds, not hours
- Team context (thoughts) surfaces automatically
- Stale flags highlight recently-changed code
- Timestamps enable root cause analysis

**Next time you see an error, don't read code. Query the graph.**

---

**For more information:**
- See [ARCHITECTURE.md](./ARCHITECTURE.md) for implementation details
- See [README.md](../README.md) for MCP tool reference
- See [GIT_INTEGRATION.md](./GIT_INTEGRATION.md) for team collaboration

**Last Updated**: 2026-02-15 (Phase 3)
