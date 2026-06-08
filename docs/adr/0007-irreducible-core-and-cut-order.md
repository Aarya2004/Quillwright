# Irreducible core and cut order

In a 10-day window the failure mode is "six features at 70%, none at 100%." To prevent it we define the **irreducible core** that must reach 100% before anything else is touched, and everything beyond it is layered on in priority order and cut from the end if time runs short.

**Irreducible core (must ship, polished):** Capture (photos + voice) → the supervised tool-using agent builds a correct itemized Estimate live (honoring Facts-from-Tools) → one Agent Pause + one human Interrupt → inline-editable Estimate → PDF export. **Private Stack only (single Mode).** This is exactly the hero demo narrative ("it does my dreaded paperwork").

**Layer order after the core is flawless (each independently shippable, cut from the end):**

1. Multilingual language toggle (Aya) — the Cohere/Toronto closing beat.
2. Profile + Episodic memory + Recall — the "learns your business" differentiator.
3. Second Mode (Best Stack) + JSON export.
4. CORD/SROIE fine-tune + eval (🎯).
5. Service-report mode.
6. Live video capture.
7. FLUX visuals.
8. Secondary pages — Dashboard / Active Jobs / Inventory (ADR-0010), each **demoable-first** (seeded → functional; the functional half cuts from the end, page by page).
9. `gr.Workflow` orchestra demo (separate stretch artifact).
   (llama.cpp Airplane-Mode Proof can be produced in parallel as a filmed artifact once the Private Stack runs.)

**Page-staging rule (ADR-0010):** any page that has a "demoable" and a "functional" form ships its demoable form FIRST (seeded data, wired into nav, looks real on camera); its functional form is started only once that page is demoable AND the core + deployment are solid. This makes "demoable-first" the hard gate even within a single feature.

## Consequences

- Build sequencing must make the core a complete vertical slice first; later layers attach without rewiring it.
- "Cuttable" is a feature, not a failure: the demo and submission are designed to be compelling with the core alone.
- This ordering supersedes any implied "build everything" reading of earlier ADRs; those features remain designed, but their delivery is conditional.
