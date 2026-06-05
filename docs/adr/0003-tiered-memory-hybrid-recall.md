# Tiered memory: Profile + Episodic with hybrid Recall

FieldForge persists two long-term memory layers on top of the short-term run-state (working memory). **Profile Memory** is a small per-tech record (trade, common Line Items, markup, report tone, language) read at the start of a Run and updated after. **Episodic Memory** is an append-only store of past Runs the agent can **Recall** via the `search_past_jobs` Tool. Recall is hybrid: a keyword/structured pre-filter (trade, equipment, model number, item names) followed by a semantic re-rank. The Embedding for the semantic step is a Model Role that swaps by Mode (small local embedder in Local Mode, Cohere Embed in Connected Mode), consistent with ADR-0001.

## Considered Options

- **No persistent memory (user picks trade):** simplest, but forfeits the "agent learns your business" differentiator.
- **Profile only:** small and safe but no cross-job recall.
- **Profile + Episodic (chosen):** strong "it learns" story, bounded scope.
- **Full Hermes-style incl. procedural Skill Documents:** most impressive but high risk of consuming the 10-day timeline; deferred.
- **Recall = keyword only / semantic only / hybrid:** hybrid chosen — keyword keeps it cheap/offline-deterministic, semantic adds fuzzy matching and a Cohere Embed tie-in.

## Consequences

- Adds an **Embedding** Model Role to the resolver (local vs Cohere Embed by Mode).
- Memory only demonstrates value across multiple Runs → the demo must pre-seed a Profile and a few past Runs to show Recall working.
- Persistence is local + human-readable (JSON/markdown), preserving the on-device/private story.
- Procedural/Skill-Document memory is explicitly out of scope for v1 (documented stretch).
