# ERP Approval Agent Migration Plan

## Active Direction

The active product direction is ERP Approval Agent Workbench, repository target identity `erp-approval-agent`.

This repo is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows. The migration should preserve the existing HarnessRuntime-owned execution lifecycle, LangGraph orchestration, harness event semantics, checkpoint/HITL concepts, and knowledge retrieval abstractions.

Historical infrastructure and observability work remains useful context. The active plan below is product migration toward ERP approval assistance.

## Non-Negotiable Architecture Anchors

- `HarnessRuntime` remains the only lifecycle owner.
- LangGraph remains the graph layer.
- existing harness events remain canonical.
- checkpoints and human-in-the-loop approval control remain durable.
- retrieval remains the abstraction for policy and business context.
- no second runtime, second agent framework, or premature ERP connector stack.

## Phase 0: Product Semantic Migration

Scope:

- README, CODEX_HANDOFF, docs, and frontend copy
- product naming and repository direction
- new ERP approval product direction document
- ERP knowledge placeholder
- no behavior change
- no full ERP domain implementation

Done when:

- public docs present ERP Approval Agent Workbench as the product identity.
- legacy RFP/security tests and benchmarks are labeled compatibility validation.
- frontend labels describe approval assistant, audit trace, evidence, approval threads, workflow tools, and policy/evidence index.
- API title is updated without route changes.

## Phase 1: LLM-First ERP Approval Graph Skeleton

Scope:

- add an `erp_approval` path kind.
- add minimal graph nodes next to existing graph paths.
- no real ERP connector yet.
- use mock approval context.
- produce structured output from the LLM.

Target output fields:

- status
- recommendation
- confidence
- missing_information
- risk_flags
- citations
- proposed_next_action

Status: complete.

Done:

- the graph can route an ERP approval prompt into a minimal ERP approval path.
- output is structured and self-checked.
- existing legacy paths and tests still work.

## Phase 2: Read-Only ERP Context Adapters

Scope:

- read-only adapter interface.
- mock connector first using local fixture data.
- later SAP, Dynamics, Oracle, and custom ERP adapter interfaces.
- normalize all outputs into evidence/context records.
- keep connector responses read-only.

Done when:

- adapters produce normalized request, supplier, invoice, PO, policy, budget, and history records.
- retrieval can include mock ERP policy and business context.
- no write actions exist yet.

Status: complete.

## Phase 3: ERP Recommendation HITL Gate

Scope:

- recommendation review through existing HITL UI.
- approve, reject, and edit decisions only.
- durable resume.
- auditable approval trace.
- no ERP action execution.

Done when:

- approval recommendations are reviewable in the UI.
- HITL decisions resume the graph deterministically.
- approval sessions can survive refresh/restart where existing checkpoint persistence supports it.
- HITL approve is documented and rendered as accepting the agent recommendation only.

Status: complete for recommendation review. Broader action cards remain Phase 4+ work.

## Phase 4: Guarded ERP Action Proposal Skeleton

Scope:

- proposed-only action drafts.
- request-more-info, internal comment, route-to-manager/finance/procurement/legal, and manual-review proposal types.
- deterministic idempotency key and fingerprint.
- validation against unsupported citations, invalid action types, and execution-like payloads.
- no ERP write action execution.

Done when:

- action proposals are separated from action execution.
- final answers show proposal id, action type, status, idempotency key, and `executable=false`.
- validation warnings are visible.
- no proposal is wired to `capability_invoke`.

Status: complete for proposed-only skeleton. Real guarded write execution remains future work.

## Phase 5: Management Efficiency Analytics

Scope:

- bottlenecks.
- missing-document patterns.
- approval SLA.
- policy friction.
- high-risk approval clusters.

Done when:

- approval traces can be summarized into operational analytics.
- metrics distinguish recommendation quality, queue delay, missing context, and escalation drivers.
- analytics remain grounded in stored approval events and evidence records.

## Historical Infrastructure Notes

The previous infrastructure plan introduced useful runtime foundations:

- runtime backend abstractions for sessions, traces, queueing, and HITL persistence.
- Redis and Postgres backend options.
- `/metrics`, OTel spans, Grafana dashboard, and alert artifacts.
- benchmark and live-validation harness metadata.

These are infrastructure capabilities, not the active product identity. Future ERP phases should reuse them without rewriting the lifecycle model.
