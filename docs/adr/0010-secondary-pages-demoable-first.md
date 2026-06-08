# Secondary pages (Dashboard / Active Jobs / Inventory): demoable-first, then functional

FieldForge gains three persistence-backed pages alongside the hero estimate **Workspace**: a **Dashboard / System Overview** (KPI cards + revenue), an **Active Jobs List** (table of past Runs), and **Inventory / Parts** (stock view). The target is _real and functional_ pages — but the governing, **non-negotiable** constraint is **demoable-first**: every page must look and feel real on camera before any live-functional work begins.

This partially relaxes the spec's "not a system of record" non-goal (these pages aggregate/persist over the existing memory store). It does NOT reintroduce CRM, scheduling, dispatch, or payments — those remain hard non-goals.

## The two-stage rule (stage 1 gates stage 2)

Each page ships in two stages, and a page's **stage 2 is started only once that page's stage 1 is done AND the Irreducible Core (Capture→Estimate→edit→PDF) + deployment are solid**:

1. **Demoable** — renders beautifully, populated from _seeded_ data (existing memory Runs + a sample inventory JSON), wired into nav. Looks real on the demo video.
2. **Functional** — live persistence/aggregation.

Functional depth cuts from the end, **page by page**, under time pressure (ADR-0007 cut order). Worst case: three real-looking seeded pages on camera. Best case: fully live.

## Per-page functional target

- **Dashboard / System Overview** — functional = a **read-model** aggregating past Runs (counts, revenue). Cheap: rides on the memory store we already persist.
- **Active Jobs List** — functional = a **read-model** listing/filtering past Runs. Same store, also cheap.
- **Inventory / Parts** — functional target is **read-only**: real stock levels + "low stock" reads from a seeded inventory JSON. **Live decrement** (finalizing an estimate subtracts parts; reorder mutates stock) is a **stretch only**, because it couples inventory ↔ estimate ↔ catalog and adds demo-failure surface.

## Considered Options

- **Demo chrome only (static):** safest, but forfeits the honest "real product" story the user wants.
- **Fully functional incl. live inventory decrement:** most impressive but couples three subsystems and risks the timeline + on-camera breakage.
- **Demoable-first, read-models functional, inventory read-only (chosen):** "real and functional" is true across all three (Dashboard/Jobs ride the existing memory store; Inventory does real stock reads) without the coupling tarpit, and demoable-first guarantees a clean video regardless of how far functional work gets.

## Consequences

- Dashboard + Active Jobs are read-models over the **existing** episodic/profile memory — minimal new storage.
- Inventory introduces one new **seeded JSON** store (read-only); a live-decrement upgrade is fenced as a late stretch.
- Nav/routing in the bespoke `gr.Server` frontend gains these three routes (still the 🎨 Off-Brand custom UI — `gr.Workflow` is explicitly NOT used here; it is a separate low-priority stretch artifact).
- Submission copy may honestly call FieldForge a multi-job workspace, but must NOT claim CRM/scheduling/payments.
