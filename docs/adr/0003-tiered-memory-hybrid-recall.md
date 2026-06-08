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

## Update 2026-06-08 — semantic re-rank made real (de-risked)

We are building the semantic half (currently keyword-only) using **`nvidia/llama-nemotron-embed-1b-v2`** — the **text** embedder (NOT the `-VL` vision-language variant, which we rejected). De-risk research confirmed the serving path:

- **Served via `sentence-transformers`** (`SentenceTransformer("nvidia/llama-nemotron-embed-1b-v2", trust_remote_code=True).encode(text)`), the model card's recommended local method. **Not Ollama** (no `/api/embeddings` support) and **not llama.cpp** (community GGUF exists but is unproven for this arch). Runs fully offline on-device → 🔌 Off the Grid preserved; adds NVIDIA breadth.
- **Architecture fit is clean:** the upgrade lives entirely behind `Memory.recall()`'s existing signature (`memory.py`) — no call-site changes in `api/estimate.py`. The resolver gains an `"embedding"` role mirroring the existing ones.
- **Cost / tradeoff (accepted):** pulls a new heavy in-process dependency (`torch` + `transformers` + `sentence-transformers`, ~2GB) into the venv — a departure from the "all models out-of-process via Ollama HTTP" pattern. Mitigated by **embedding at record-time and caching the 2048-d vector per Run in the JSON**; at recall time only the _query_ is embedded + cosine in NumPy, so torch stays out of the hot path. (Fallback if torch is a dealbreaker: community GGUF via llama.cpp — unproven, riskier; only if needed.)
- **Viability gate is the accuracy question:** with ~5 seeded Runs semantic vs keyword is indistinguishable. To answer "does it improve accuracy" (and to earn a second measured Field-Notes data point), seed ~15–20 Runs + a small Recall eval (queries where keyword fails but meaning matches; measure recall@1 keyword vs semantic). The eval is recommended-but-optional; the working semantic Recall ships regardless. Per ADR-0007 this is a layer — attaches without rewiring the core, cuts from the end.
