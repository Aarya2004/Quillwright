# Frontend — Core Workspace (the Forge Estimate screen)

Visual target for the Irreducible Core UI, built faithfully in **Gradio** with custom CSS (not raw Tailwind). Source: user's Tailwind mockup, with non-functional elements removed per the "every element needs a purpose" rule.

## Layout (the one screen the core builds)

```
┌─ Top bar ─────────────────────────────────────────────────────────────┐
│  Forge Estimate: AC Unit Repair — 123 Maple St        (title only)     │
├───────────────────────────┬───────────────────────────────────────────┤
│ LEFT 40% · dark #10191E    │ RIGHT 60% · light surface                 │
│ ⌁ AI Forge: Working…  ●(g) │ Draft Estimate        [+ Add Item][PDF]   │
│ ─ streaming Trace ─        │ ┌───────────────────────────────────────┐ │
│ ✓ Analyzing voice note…    │ │ Description │ Details │ Qty │ Rate │ $ │ │
│ ✓ Processing photos [▤][▤] │ │ 45+5 Capacitor │ part │ 1 │ 42.50│…│ │
│ ✓ Identified: capacitor    │ │ Contactor      │ …    │ 1 │ 28.00│…│ │
│ ● Fetching pricing… ▌       │ │ Labor (pulsing while building)        │ │
│   (JetBrains Mono, cursor) │ └───────────────────────────────────────┘ │
│                            │ ┌ Agent-Pause card (conditional) ───────┐ │
│                            │ │ 🤖 Standard or Silver Duty? [S][Silver]│ │
│                            │ └───────────────────────────────────────┘ │
│                            │                 Subtotal / Tax / Total    │
├───────────────────────────┴───────────────────────────────────────────┤
│ [🌐 Generate Customer Copy ▾]        Discard Draft  [Finalize & Send →]│
└───────────────────────────────────────────────────────────────────────┘
```

## Components (Gradio mapping)
- **Top bar:** `gr.Markdown`/`gr.HTML` with the job title. Title only.
- **Left log pane:** a streaming `gr.HTML` block re-rendered as TraceSteps arrive — check-circles for done steps, a pulsing dot + terminal-cursor on the active step, inline photo thumbnails, JetBrains Mono. Dark bg `#10191E`.
- **Right estimate:** editable `gr.Dataframe` (Description, Details, Qty, Rate, Amount) — edits recalc totals. Header buttons: **Add Item**, **Preview PDF**.
- **Agent-Pause card:** a conditional `gr.HTML`/group with the agent's question + answer buttons; visible only while the graph is interrupted; resolves the LangGraph interrupt.
- **Financial summary:** subtotal / tax / total (right-aligned).
- **Footer:** language dropdown (**Generate Customer Copy** → English/Spanish/French, drives Aya later), **Discard Draft**, **Finalize & Send**.

## Theme tokens (custom CSS)
- Primary orange `#964900` (dark) / `#f57c00` (accent/cursor); on-primary white.
- Surfaces: light `#f7fafc`; log pane dark `#10191E`, borders `#1C2931`.
- Fonts: Hanken Grotesk (headings), Inter (body), JetBrains Mono (log).
- Done-step green `#22c55e`; rounded corners; subtle shadows.

## Removed (no purpose in the core; re-add when pages exist)
- SideNavBar (Dashboard/Active Jobs/Parts Catalog/Team/Support/Logout) and mobile BottomNav — navigate nowhere yet.
- Top-bar notifications, settings, profile avatar — no such systems.
- "LIVE SYNC" pill (the pulsing dot already signals liveness); "Edit Manual" (table is directly editable).

## Honesty disclaimer
Kept in the **PDF footer** ("AI-generated draft · sample pricing · review before sending"); no on-screen banner for now (keeps the live screen clean). Revisit later.

## Notes for build
- Core uses stubbed perception, so the photo thumbnails + "Identified: …" steps are driven by the stub's scripted observations in early builds; real vision model swaps in via the resolver.
- "Generate Customer Copy" (multilingual) is wired in the layer after the core (ADR-0007 cut order) — render the control now, activate with Aya later.
