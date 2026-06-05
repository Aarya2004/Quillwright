# Interruptible agent via shared state, edits applied between steps

The Agent Brain runs a Run as discrete steps (plan → call Tool → observe → next). Supervision is bidirectional: the agent can **Agent Pause** to ask the human for a low-confidence/missing decision, and the human can **Interrupt** at any time (edit a Line Item, correct an Observation, redirect). Both work through a single shared run state: the human's change is written to state immediately, and the agent reads the updated state at the start of its NEXT step and re-plans from there. We deliberately do NOT attempt true mid-step preemption (cancelling an in-flight model call mid-token).

## Considered Options

- **Apply edits between steps (chosen):** robust, no half-finished-step corruption, achievable in 10 days; with short steps (1-3s) it feels seamless.
- **True mid-step preemption:** most "alive" but requires in-flight cancellation + re-planning from arbitrary points; too many demo-breaking edge cases for the timeline.
- **Pause-to-edit-then-resume:** safest but loses the "barge in while it runs" magic the user wanted.

## Consequences

- Need a single mutable run-state object the UI and agent both read/write; the agent must re-derive its next step from current state each iteration (not from a fixed pre-baked plan).
- Steps should be kept short so the "next step picks up the edit" latency feels instant.
- The Trace must reflect human Interrupts inline so the recorded Trace stays honest.
