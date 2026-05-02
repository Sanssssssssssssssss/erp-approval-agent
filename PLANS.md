# ERP Approval Agent Migration Plan

## Active Direction

The active product direction is ERP Approval Agent Workbench, repository target identity `erp-approval-agent`.

This repo is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows. The migration should preserve the existing HarnessRuntime-owned execution lifecycle, LangGraph orchestration, harness event semantics, checkpoint/HITL concepts, and knowledge retrieval abstractions.

Historical infrastructure and observability work remains useful context. The active plan below is product migration toward ERP approval assistance.

Post-Phase-14 evidence-first hardening is complete: the core has been audited with 82 fictional toy approval cases using a strict local reviewer harness. The audit is regression/self-critique only, not a production benchmark. A local sample evidence pack now lives under `knowledge/ERP Approval/sample_evidence`, and `reports/evaluations/manual_agent_smoke_latest.md` manually verifies the real agent path displays approval forms, invoice/PO/GRN, receipts, quote, budget, vendor, and policy evidence before recommendations.

The newest active product correction is CaseHarness: every user turn is a controlled case-state patch. Chat is only the interface. `case_state.json`, `dossier.md`, local evidence files, and `audit_log.jsonl` are the source of truth for multi-turn approval review. Future phases should keep these audits hard, add difficult cases rather than loosening expected outcomes, and preserve the rule that invalid or off-topic turns must not pollute the case.

The CaseHarness pressure suite at `backend/benchmarks/erp_approval_case_harness_stress.py` should be treated as an active regression guard. It currently covers 66 messy scenarios and 74 turns, including weak oral evidence, prompt injection, off-topic turns, execution-boundary probes, and multi-turn evidence submission.

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

## Phase 5: ERP Approval Trace Ledger + Analytics Foundation

Scope:

- local JSONL trace ledger for ERP approval runs.
- trace records built from structured graph state, not final answer parsing.
- read-only trace listing, trace detail, and analytics summary API.
- frontend management Insights tab.
- missing-document, risk-flag, guard-warning, review-status, and proposal outcome summary counts.

Done when:

- approval traces can be summarized into operational analytics.
- analytics remain grounded in stored structured trace records.
- trace writes do not break final answer delivery if storage fails.
- no write endpoint or ERP action execution is introduced.

Status: complete for local trace ledger and lightweight read-only analytics foundation. This is not a benchmark, process-mining system, or ERP connector.

## Phase 6: ERP Approval Trace Explorer + Read-Only Analytics Refinement

Scope:

- trace filters by approval type, recommendation status, review status, and date.
- lightweight export for audit review.
- richer trace drill-down in the frontend.
- trend views for missing-document patterns, policy friction, escalation drivers, and high-risk clusters.
- keep all analytics read-only and grounded in structured trace records.

Done when:

- managers can review stored ERP approval trace summaries without touching ERP systems.
- analytics remain clearly separated from benchmark accuracy claims.
- no approval write action is introduced.

Status: complete for trace filters, detail lookup, JSON/CSV export, date-bucket trend summaries, and frontend drill-down.

## Phase 7: ERP Action Proposal Ledger + Read-Only Audit Package

Scope:

- proposed-only action proposal ledger.
- persist proposal idempotency fields, payload preview, validation warnings, and non-action statement.
- read-only proposal list/detail and per-trace proposal lookup.
- temporary audit package generated from traces and proposals.
- lightweight completeness checks on trace/proposal auditability.
- no ERP write execution.

Done when:

- reviewers can package a set of traces for internal review without modifying ERP data.
- exports remain grounded in structured trace records.
- action proposal ledger remains separate from any execution ledger.
- no benchmark or process-mining claim is introduced.

Status: complete for proposal ledger, per-trace proposal records, audit package endpoint, completeness checks, and frontend audit package download.

## Phase 8: Local Audit Package Workspace + Reviewer Notes

Scope:

- saved audit package manifests with package snapshots and stable hashes.
- append-only reviewer notes stored locally.
- package metadata and reviewer notes stored locally without ERP writes.
- package export views for internal review meetings.
- no action execution.

Done when:

- reviewers can save and revisit read-only audit packages.
- saved packages remain local filesystem artifacts.
- no ERP connector or action API is introduced.

Status: complete for saved package manifests, package snapshot export, append-only reviewer notes, local workspace APIs, and frontend workspace.

## Phase 9: Mock Action Simulation Sandbox + Local Simulation Ledger

Scope:

- local dry-run simulation records for action proposals.
- simulation requests must reference a saved audit package and proposal record.
- validation requires `confirm_no_erp_write=true`.
- all records keep `simulated_only=true` and `erp_write_executed=false`.
- store records in local JSONL only.
- no ERP write execution.

Done when:

- reviewers can dry-run a proposed future action path without touching ERP systems.
- simulations are clearly separate from execution records.
- no capability invocation or action execution endpoint is introduced.

Status: complete for local simulation models, validation, JSONL ledger, local simulation API, tests, and frontend sandbox.

## Phase 10: Read-Only ERP Connector Interface + Connector Registry

Scope:

- read-only connector models and protocol.
- connector registry defaulting to mock.
- provider profile metadata for SAP S/4HANA OData, Dynamics 365 F&O OData, Oracle Fusion REST, and custom HTTP JSON.
- disabled HTTP read-only connector skeleton with test-injected transport.
- `erp_context_node` consumes connector results as context records.
- no live ERP network access by default.
- no ERP write execution.

Done when:

- mock remains the default connector.
- non-mock connectors are disabled and network-blocked by default.
- all connector outputs normalize into approval context records.
- tests use fake transport only and never call SAP/Dynamics/Oracle.
- no action execution ledger is introduced.

Status: complete for connector interface, registry, mock connector, provider profiles, HTTP skeleton, executor context-node integration, and connector tests.

## Phase 11: Read-Only Connector Configuration Hardening

Scope:

- typed environment loading for connector config.
- explicit connector selection tests with network disabled by default.
- redacted diagnostics and healthcheck UI/API.
- fixture-driven schema mapping examples for provider profiles.
- no ERP write execution.
- default provider remains mock.
- non-mock provider profiles require explicit read-only opt-in and separate network opt-in.

Done when:

- connector configuration can be inspected locally without exposing secrets.
- non-mock connectors remain disabled unless explicitly configured.
- connector health/profile APIs are GET-only and do not trigger live ERP calls.
- SAP/Dynamics/Oracle/custom payload examples map into `ApprovalContextRecord` without claiming production schema coverage.
- no write operation or action execution path exists.

Status: complete for typed env loading, explicit opt-in gates, redacted config summaries, connector diagnostics, GET-only health/profile APIs, provider mapping fixtures, and HTTP connector mapper integration. `GRAPH_VERSION` is now finalized as `phase14`.

## Phase 12: Read-Only Connector Fixture Replay / Configuration UX

Scope:

- local fixture replay harness for connector mapping confidence.
- frontend and API surface for inspecting connector profiles and diagnostics.
- fake transports and fixture payloads only.
- no real ERP network access by default.
- no ERP action execution.

Done when:

- reviewers can inspect connector readiness and mapping behavior locally.
- all diagnostics remain redacted.
- connector work still produces context records only.

Status: complete for local fixture replay models/service, GET-only replay API, redaction of sensitive query params, frontend connector diagnostics panel, and replay validation.

## Phase 13: Read-Only Connector Mapping Coverage Expansion + Replay Coverage Matrix

Scope:

- add more representative fixture payloads for read-only operations beyond purchase requisition.
- keep all mapping examples local and non-production.
- add a local replay coverage matrix for provider, operation, fixture, and mapper output completeness.
- expose a GET-only coverage API and frontend diagnostics view.
- no live ERP network access.
- no ERP action execution.

Done when:

- more connector operation shapes can be inspected locally.
- mapper coverage remains explicit and conservative.
- no connector is treated as an action executor.

Status: complete for four-provider by eight-operation fixture coverage, operation-specific entity id extraction, GET-only replay coverage API, tests, and frontend coverage diagnostics.

## Phase 14: Final MVP Closure

Scope:

- documentation consistency pass.
- MVP acceptance checklist.
- final validation command/script.
- release boundary tests.
- final MVP report.
- `GRAPH_VERSION=phase14`.
- explicit STOP rules.
- no connector expansion.
- no simulation expansion.
- no audit workspace expansion.
- no mapper diagnostics or profile notes.
- no benchmark.
- no live ERP connection.
- no ERP write action.

Done when:

- `docs/product/mvp_acceptance_checklist.md` states accepted MVP scope and boundaries.
- `backend/scripts/dev/validate-phase14-mvp.ps1` runs the final validation suite.
- release boundary tests guard graph version, ERP API methods, connector GET-only surface, no execution/live-test routes, and no `approval.*` event namespace.
- final MVP report records validation results.
- STOP rules are documented for future Codex agents.

Status: complete for final MVP closure.

## Evidence-First Case Agent Refactor

Scope:

- convert the ERP approval core from recommendation-centric to evidence-case-centric.
- add case file, evidence requirements, evidence artifacts, evidence claims, sufficiency gate, contradiction detection, control matrix, case-grounded recommendation, and adversarial review.
- treat one-sentence user input as a case draft only.
- keep all Phase 14 boundaries: no live ERP, no network, no ERP writes, no capability invocation, no benchmark claim.

Done when:

- missing blocking evidence prevents `recommend_approve`.
- final answers show Required evidence checklist, Evidence claims, Evidence sufficiency, Contradictions, Control matrix checks, Risk assessment, Adversarial review, Recommendation, and Non-action boundary.
- tests prove purchase requisition, invoice payment, supplier onboarding, contract exception, and budget exception cases cannot pass without required evidence.

Status: complete for local evidence-first case analysis and graph refactor.

## Historical Infrastructure Notes

The previous infrastructure plan introduced useful runtime foundations:

- runtime backend abstractions for sessions, traces, queueing, and HITL persistence.
- Redis and Postgres backend options.
- `/metrics`, OTel spans, Grafana dashboard, and alert artifacts.
- benchmark and live-validation harness metadata.

These are infrastructure capabilities, not the active product identity. Future ERP phases should reuse them without rewriting the lifecycle model.
