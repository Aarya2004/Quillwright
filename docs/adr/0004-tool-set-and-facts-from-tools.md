# Tool set and the Facts-from-Tools correctness rule

The Agent Brain operates through a fixed v1 Tool set: `perceive`, `search_past_jobs`, `lookup_price`, `compute`, `draft_line_item`, `flag_for_human`, `translate`, `update_profile`. The governing principle is **Facts-from-Tools**: every number that reaches the customer (price, quantity, markup, tax, total) must originate from a Tool or user-confirmed data — the Brain may route, judge, and phrase, but may not generate figures. `translate` has two entry points (the UI language toggle and autonomous agent calls) backed by one function, so no two components own translation.

## Considered Options

- **Lean 4 tools** (perceive, lookup_price, compute, flag_for_human): simplest, but folds Recall and structured drafting into LLM reasoning — weaker structure guarantees and a thinner "tool-using agent" story.
- **Core 6** (adds search_past_jobs, draft_line_item): covers the loop honestly.
- **Core 6 + translate + update_profile (chosen):** makes multilingual and learning agent-driven; 8 small, individually testable tools.

## Consequences

- More tools = more reliability surface on a small model; each tool gets unit tests and the agent's tool-selection is exercised by trace assertions.
- Facts-from-Tools is the testable invariant behind the "honest, no fabricated numbers" pitch — assert no customer-facing number lacks a Tool/user-confirmed provenance.
- `compute` is deterministic (no LLM math); `lookup_price` is catalog/Profile-backed; novel un-priced items route to `flag_for_human`, never an LLM guess.
