# ERP Approval Agent Product Plan

This document describes the target direction for ERP Approval Agent Workbench and the current phased implementation state.

## Product Goal

ERP Approval Agent Workbench should help enterprise approvers review ERP business requests with LLM-first approval reasoning, retrieved ERP policy and business context, human-in-the-loop approval control, and an auditable approval trace.

The product should recommend next actions. It must not autonomously execute final ERP approvals without strict HITL governance.

Current implementation:

- Phase 1 LLM-first ERP approval graph skeleton exists.
- Phase 2 read-only mock ERP/policy context adapter exists.
- Phase 3 durable ERP recommendation review HITL gate exists.
- no real ERP connector exists.
- no real approval write action exists.
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
-> erp_reasoning
-> erp_guard
-> erp_hitl_gate
-> erp_finalize
-> finalize
```

Phase 3 uses the existing LangGraph checkpoint/HITL resume mechanism to review agent recommendations. Future phases can expand this into richer retrieval, action proposals, and audited guarded write execution.

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

## Non-Goals For Early Phases

- no real SAP, Dynamics, Oracle, or custom ERP connector in early phases.
- no production ERP write actions in early graph skeleton and HITL review work.
- no autonomous approve/reject behavior.
- no benchmark-proven ERP approval accuracy claim until ERP benchmark suites exist.
- no broad runtime rewrite.
- no second agent framework.

## Why HarnessRuntime And LangGraph Remain

`HarnessRuntime` should remain the lifecycle owner because it already owns canonical run events, session behavior, trace emission, and HITL/checkpoint integration.

LangGraph should remain the graph layer because ERP approval reasoning benefits from explicit stages: intake, retrieval, policy context, reasoning, self-check, HITL gate, action proposal, and audit finalization.

The existing knowledge retrieval and context abstractions should remain because ERP approvals need policy and business context retrieval without coupling the runtime to a specific connector or index. Phase 2 introduces read-only adapter interfaces first, with mock context records only.
