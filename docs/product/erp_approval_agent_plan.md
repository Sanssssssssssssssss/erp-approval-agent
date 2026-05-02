# ERP Approval Agent Product Plan

This document describes the target direction for ERP Approval Agent Workbench and the current phased implementation state.

## Product Goal

ERP Approval Agent Workbench should help enterprise approvers review ERP business requests with LLM-first approval reasoning, retrieved ERP policy and business context, human-in-the-loop approval control, and an auditable approval trace.

The product should recommend next actions. It must not autonomously execute final ERP approvals without strict HITL governance.

Current implementation:

- Phase 1 LLM-first ERP approval graph skeleton exists.
- Phase 2 read-only mock ERP/policy context adapter exists.
- Phase 3 durable ERP recommendation review HITL gate exists.
- Phase 4 guarded action proposal skeleton exists.
- Phase 5 local trace ledger and read-only analytics foundation exists.
- Phase 6 read-only trace explorer with filters, export, drill-down, and trend summaries exists.
- Phase 7 proposed-only action proposal ledger and read-only audit packages exist.
- Phase 8 local audit package workspace and reviewer notes exist.
- Phase 9 local action simulation sandbox and simulation ledger exist.
- Phase 10 read-only ERP connector interface and registry exist.
- Phase 11 read-only connector configuration hardening, redacted diagnostics, health/profile APIs, and provider mapping fixtures exist.
- Phase 12 read-only connector fixture replay and diagnostics UX exist.
- Phase 13 read-only connector mapping coverage expansion and local replay coverage matrix exist.
- Phase 14 final MVP closure, acceptance checklist, release boundary tests, final validation script, final report, and STOP rules exist.
- evidence-first case analysis exists: case files, evidence requirements, evidence claims, sufficiency gate, contradictions, control matrix, case recommendation, and adversarial review now sit before guard/HITL.
- no live ERP connector is enabled by default.
- no real approval write action exists.
- no real comment/request-more-info/routing write action exists.
- no ERP approval/rejection/payment/supplier/contract/budget execution exists.

## Enterprise Approval Scenarios

- purchase requisition
- expense approval
- invoice/payment review
- supplier onboarding
- contract exception review
- budget exception review

## LLM-First Approval Reasoning

The future approval path should use prompt engineering and structured LLM outputs as the main reasoning mechanism. The graph should provide execution boundaries, checkpoints, evidence retrieval, HITL gates, and audit events.

LLM reasoning should evaluate:

- business justification
- policy alignment
- budget availability or exception status
- vendor/supplier risk signals
- missing documentation
- approval authority and escalation needs
- irreversible action risk

## Graph Workflow

Current implemented graph:

```text
bootstrap
-> route
-> skill
-> memory_retrieval
-> erp_intake
-> erp_context
-> erp_case_file
-> erp_evidence_requirements
-> erp_evidence_claims
-> erp_evidence_sufficiency
-> erp_control_matrix
-> erp_case_recommendation
-> erp_adversarial_review
-> erp_guard
-> erp_hitl_gate
-> erp_action_proposal
-> erp_finalize
-> finalize
```

The current graph is evidence-first: a one-sentence prompt creates a case draft, then deterministic evidence requirements, claims, sufficiency, contradiction detection, control matrix checks, case recommendation, and adversarial review run before guard/HITL. Blocking evidence gaps prevent `recommend_approve`. Phase 3 uses the existing LangGraph checkpoint/HITL resume mechanism to review agent recommendations. Phase 4 adds proposed-only action drafts after review. Phase 5 writes a local structured trace record during finalization and exposes read-only analytics summaries. Phase 6 adds trace filters, detail lookup, JSON/CSV export, and date-bucket trend summaries. Phase 7 writes proposed-only action proposal records and builds temporary read-only audit packages. Phase 8 saves local audit package manifests and append-only reviewer notes. Phase 9 records local dry-run simulations of proposed future action paths. Phase 10 routes context through a read-only connector registry that defaults to mock. Phase 11 hardens connector configuration with typed env loading, explicit read-only opt-in, redacted diagnostics, provider health/profile APIs, and fixture-based schema mapping examples. Phase 12 adds local fixture replay diagnostics for provider profile and mapper readiness without network access. Phase 13 expands those local fixtures across approval request, vendor, budget, purchase order, invoice, goods receipt, contract, and policy operations, then summarizes mapper readiness in a replay coverage matrix. Phase 14 closes the MVP boundary and adds no new connector, simulation, audit workspace, mapper diagnostic, profile note, benchmark, live ERP, or ERP write-action scope.

## Prompt-Engineering Direction

Current and target prompt structure:

- system prompt: enterprise ERP approval analyst
- context sections:
  - approval request
  - ERP records
  - policy context
  - historical context
  - user role
- output schema:
  - status
  - recommendation
  - confidence
  - missing_information
  - risk_flags
  - citations
  - proposed_next_action
- self-check:
  - unsupported claims
  - missing context
  - irreversible action check
  - escalation check

Recommended future decision statuses:

- `recommend_approve`
- `recommend_reject`
- `request_more_info`
- `escalate`
- `blocked`

## HITL And Audit Approach

The workbench should preserve a durable approval trace:

- original approval request
- retrieved business records and policy context
- LLM reasoning summary
- citations
- self-check result
- human decision
- any edited payload
- final proposed next action

Human-in-the-loop approval control should gate any action that writes to an ERP system, changes approval status, sends an external comment, or affects payment/vendor/contract state.

Current Phase 3 HITL semantics are narrower: the reviewer accepts, rejects, or edits the agent recommendation only. HITL approve does not approve, reject, pay, onboard, sign, or update any ERP object.

Current Phase 4 action proposals are also non-executing. They can describe request-more-info, internal-comment, routing, or manual-review drafts, but every proposal is `executable=false` and says no ERP write action was executed.

Current Phase 5 trace analytics are implemented as local structured JSONL records and read-only summary endpoints. Phase 6 adds a trace explorer over those records. Phase 7 adds a separate action proposal ledger and audit package builder. Phase 8 adds saved package manifests and local reviewer notes. Phase 9 adds local simulation records for proposed action paths. Phase 10 adds read-only connector interfaces and disabled provider profile skeletons. Phase 13 connector coverage is also local fixture replay only; it is mapper readiness diagnostics, not ERP integration proof. Analytics, audit packages, simulations, and connector context are derived from structured fields such as recommendation status, review status, missing information, risk flags, guard warnings, proposal idempotency fields, and proposal validation results. Text filters match structured fields such as approval ID, requester, vendor, cost center, and trace ID. They do not parse final answer text, call an ERP system by default, execute mock actions, or claim benchmark accuracy.

## Minimal Future Data Model

Early phases can use mock records with normalized context fields:

- approval_request
  - request_id
  - request_type
  - requester
  - amount
  - currency
  - cost_center
  - supplier_id
  - business_justification
  - attachments
- erp_record
  - source_system
  - entity_type
  - entity_id
  - fields
  - retrieved_at
- policy_context
  - policy_id
  - policy_name
  - section
  - text
  - applicability
- approval_recommendation
  - status
  - recommendation
  - confidence
  - missing_information
  - risk_flags
  - citations
  - proposed_next_action
- action_proposal
  - proposal_id
  - action_type
  - status
  - target
  - payload_preview
  - citations
  - idempotency_key
  - idempotency_fingerprint
  - executable
- approval_trace
  - trace_id
  - run_id
  - approval_id
  - context_source_ids
  - recommendation_status
  - review_status
  - guard_warnings
  - proposal_ids
  - proposal_action_types
  - proposal_validation_warnings
  - final_answer_preview
- analytics_summary
  - total_traces
  - recommendation_status_counts
  - review_status_counts
  - missing_information_counts
  - risk_flag_counts
  - proposal_action_type_counts
  - blocked_or_rejected_proposal_counts
- trace_query
  - approval_type
  - recommendation_status
  - review_status
  - proposal_action_type
  - human_review_required
  - guard_downgraded
  - high_risk_only
  - text_query
  - date_from
  - date_to
- trend_summary
  - bucket_field
  - buckets
- action_proposal_record
  - proposal_record_id
  - proposal_id
  - trace_id
  - approval_id
  - action_type
  - payload_preview
  - idempotency_key
  - idempotency_scope
  - idempotency_fingerprint
  - executable
  - validation_warnings
- audit_package
  - package_id
  - trace_ids
  - proposal_record_ids
  - traces
  - proposals
  - completeness_checks
  - non_action_statement
- saved_audit_package_manifest
  - package_id
  - title
  - package_hash
  - package_snapshot
  - completeness_summary
  - note_count
- reviewer_note
  - note_id
  - package_id
  - author
  - note_type
  - body
  - non_action_statement
- action_simulation_record
  - simulation_id
  - proposal_record_id
  - package_id
  - approval_id
  - action_type
  - status
  - idempotency_key
  - idempotency_fingerprint
  - output_preview
  - simulated_only
  - erp_write_executed
  - non_action_statement
- erp_connector_config
  - provider
  - mode
  - enabled
  - allow_network
  - base_url
  - tenant_id
  - company_id
  - timeout_seconds
  - auth_type
  - auth_env_var
  - explicit_read_only_opt_in
  - use_as_default
- erp_read_result
  - provider
  - status
  - records
  - warnings
  - diagnostics
  - non_action_statement
- erp_connector_diagnostic
  - provider
  - selected_as_default
  - status
  - warnings
  - redacted_config
  - auth_env_var_present
  - forbidden_methods
  - non_action_statement
- erp_connector_replay_record
  - replay_id
  - provider
  - operation
  - fixture_name
  - status
  - records
  - source_ids
  - validation
  - network_accessed
  - non_action_statement
- erp_connector_replay_coverage_summary
  - total_items
  - passed_items
  - failed_items
  - by_provider
  - by_operation
  - items
  - non_action_statement

## Non-Goals For Early Phases

- no live SAP, Dynamics, Oracle, or custom ERP connector enabled by default in early phases.
- no connector diagnostics/API/logs may expose secret values.
- no non-mock connector should be selected without explicit read-only opt-in plus explicit network allowance.
- no fixture replay or replay coverage should be described as a live ERP test, benchmark, or production integration proof.
- no production ERP write actions in early graph skeleton and HITL review work.
- no action proposal is a tool call or ERP connector call.
- no autonomous approve/reject behavior.
- no benchmark-proven ERP approval accuracy claim until ERP benchmark suites exist.
- no broad runtime rewrite.
- no second agent framework.
- no process-mining or production management analytics claim in the trace foundation phase.
- no write API in trace explorer/export phases.
- no action execution API in proposal ledger or audit package phases.
- no reviewer note should be treated as an ERP comment.
- no action simulation should be treated as action execution or ERP dry-run against a live system.
- no connector profile should be described as a completed live ERP integration until explicit read-only live validation exists.

## Phase 14 STOP Rules

Phase 14 is the MVP acceptance point. Stop scope expansion here unless a future task explicitly opens a new phase.

Do not add to this MVP closure:

- connector expansion
- simulation expansion
- audit workspace expansion
- mapper diagnostics expansion
- connector profile notes
- ERP benchmark suites
- live ERP connections
- ERP write actions
- action execution APIs
- action execution ledgers
- new `approval.*` Harness events
- a second runtime or agent framework

## Why HarnessRuntime And LangGraph Remain

`HarnessRuntime` should remain the lifecycle owner because it already owns canonical run events, session behavior, trace emission, and HITL/checkpoint integration.

LangGraph should remain the graph layer because ERP approval reasoning benefits from explicit stages: intake, retrieval, policy context, reasoning, self-check, HITL gate, action proposal, and audit finalization.

The existing knowledge retrieval and context abstractions should remain because ERP approvals need policy and business context retrieval without coupling the runtime to a specific connector or index. Phase 2 introduced read-only adapter interfaces first, with mock context records only. Phase 10 adds a connector registry around that boundary while keeping mock as the default and live network access disabled. Phase 11 keeps the same boundary but makes connector selection safer and more inspectable through local redacted diagnostics. Phase 12 adds local fixture replay so provider payload examples can be mapped into `ApprovalContextRecord` records without any ERP network call. Phase 13 expands those fixtures into a coverage matrix over representative read-only operations, still using local JSON only. This is still not a live SAP, Dynamics, Oracle, or custom ERP integration.
