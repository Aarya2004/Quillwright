# LangGraph for the agent loop

The Agent Brain's loop is built on **LangGraph**. Its first-class `interrupt` primitive plus a checkpointer (InMemorySaver for our single-session use) directly implement ADR-0002's supervision design — Agent Pause, human Interrupt, and shared run-state read/written between steps — along with first-class failure/resume handling and explicit graph control over the streamed Trace. The alternative of hand-rolling this would re-implement interrupt/resume/checkpointing we'd likely get subtly wrong under a 10-day deadline.

## Considered Options

- **Hand-rolled Python loop:** total control, trivial to stub, no dependency — but re-implements interrupt/resume/checkpoint semantics from scratch (risk).
- **PydanticAI:** excellent type-safety, streaming, testability, and Pydantic Evals; HITL is more "tool approval" than "edit shared state mid-run," so we'd add our own state handling.
- **smolagents:** tiny/HF-native but code-execution-centric with no checkpoint/interrupt infra.
- **LangGraph (chosen):** its headline features ARE our ADR-0002; least likely to get supervision semantics wrong.
- **Hybrid LangGraph + PydanticAI tools:** powerful but two frameworks to learn for the core — deferred.

## Consequences

- Tools are LangGraph-dispatched nodes/functions; the resolver (ADR-0001/0005) is what each tool calls for its Model Role. Models are stubbable so unit tests need no GPU.
- The graph state is the shared run-state; the Trace is emitted from graph steps; `interrupt` raises an Agent Pause; human edits are applied to checkpointed state and resumed.
- Adds LangGraph as a core dependency (the one heavy framework we take on). Facts-from-Tools (ADR-0004) is enforced in tool implementations, independent of the framework.
- Pydantic Evals remains available later for the fine-tune eval (ADR-0006) without adopting PydanticAI for orchestration.
