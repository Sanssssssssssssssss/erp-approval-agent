# ERP Approval Case Agent Independent Review

Date: 2026-05-02

## Executive Summary

This review reran the existing evidence-first case suites and asked an independent reviewer agent to evaluate the current ERP Approval Agent from a stricter product perspective.

Result: the current system is now a credible local evidence-first approval case state machine. It is no longer merely a one-sentence approval suggestion bot. The CaseHarness can create cases, reject weak user statements, persist local case state, update dossiers, maintain audit logs, enforce the non-action boundary, and block prompt-injection or ERP execution requests.

However, the current evidence is still not enough to claim a mature LLM approval agent. Most automated benchmarks are still generated from the same rules the system implements. The newly split model roles are architecturally correct, but the main benchmark suite does not yet run systematic live-model or shadow-model evaluation.

Recommended next phase: Stage Model Shadow Evaluation plus realistic evidence attachment benchmark.

## Commands Run By Main Thread

```powershell
backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend
```

Result:

- ERP MVP tests: 161 tests passed.
- strict evidence-case toy audit: 82/82 passed, 0 critical, 0 major.
- manual ERP smoke: 9/9 passed.
- CaseHarness stress suite: 66/66 scenarios passed, 74 turns, 0 critical, 0 major.
- maturity benchmark: 321 cases, 417 turns, average 99.85, 321 A grades.
- legacy RFP/security compatibility: 11 tests passed.
- py_compile: passed.
- LangGraph compiler smoke: passed.
- git diff --check: passed.

## Live Stage-Model Smoke

The local environment had a configured OpenAI-compatible model:

- provider: openai
- model: kimi-k2.5
- API key present: yes
- base URL present: yes

A small live stage-model case turn was executed with `CaseStageModelReviewer` against a fictional quote for `PR-LIVE-001`.

Observed result:

- `patch_type`: `reject_evidence`
- `evidence_decision`: `rejected`
- `accepted_evidence_count`: 0
- `rejected_evidence_count`: 1
- `model_used`: true
- role outputs present:
  - `turn_classifier`
  - `evidence_extractor`
  - `policy_interpreter`
  - `contradiction_reviewer`
  - `reviewer_memo`
- model warnings included:
  - quote lacks validity date and signer.
  - current evidence completeness is low.
  - vendor onboarding and supplier risk evidence are not verified.
- non-action boundary preserved: `This is a local approval case state update. No ERP write action was executed.`

Interpretation: the live model role loop can run and can be stricter than deterministic extraction. This is promising, but it is only a smoke test, not a benchmark.

## Independent Reviewer Results

An independent reviewer agent ran the same suites into a temporary output directory and did not modify repository files.

Independent commands and results:

- strict toy audit: `cases=82 passed=82 failed=0 critical=0 major=0`
- manual smoke: `manual ERP smoke: 9/9 passed`
- CaseHarness stress: `scenarios=66 turns=74 passed=66 failed=0 critical=0 major=0 minor=0 usability_notes=21`
- maturity benchmark: `cases=321 turns=417 average=99.85 p10=100.00 A=321 critical=0 major=0`
- targeted tests: `Ran 27 tests ... OK`

## What Looks Good

- Case turns are stateful and write local case artifacts instead of free-form chat memory.
- Weak user statements, prompt injection, off-topic input, and execution-like requests are blocked.
- `No ERP write action was executed` is consistently preserved.
- `CasePatchValidator` remains the writer boundary.
- Model role split is the right architecture: model proposes, validator writes.
- The live smoke showed the model can reject insufficient quote evidence and ask for missing materials.
- HarnessRuntime now owns `/cases/turn` execution lifecycle.

## Main Risks

### 1. Benchmark Self-Certification

The strict toy audit, stress suite, and maturity benchmark mostly test against requirements and controls authored in this repository. They prove internal consistency, not production approval quality.

### 2. Model Roles Are Not Yet Systematically Evaluated

The main suites still run deterministic CaseHarness by default. Fake model tests prove role order and hard-gate behavior, while the live smoke proves the path can run. But there is not yet a large shadow benchmark comparing:

- deterministic baseline
- stage-model proposal in shadow mode
- stage-model enabled write path

### 3. Mock Complete Context Can Still Feel Like One-Turn Approval

If mock context already contains complete evidence, a first-turn review can reach `recommend_approve` / `ready_for_final_review`. Technically this is because the mock connector supplied evidence, not because the user sentence was enough. But the UI must make that evidence chain obvious or users will still perceive it as "one sentence passed."

### 4. Too Many Missing-Evidence Cases Escalate

The stress suite showed `request_more_info_turns=0`. Conservative escalation is safe, but a mature approval assistant should often say exactly what to submit next instead of escalating every incomplete case.

### 5. UX Still Needs Evidence-Submission Friction

The backend can reject weak material, but the front-end should make the workflow feel like a case workspace:

- current required materials
- upload/paste evidence by requirement
- accepted evidence
- rejected evidence
- next missing items
- dossier preview
- final reviewer memo only when ready

### 6. Maturity Benchmark Has Ceiling Effect

321 A grades and average 99.85 means the rubric is no longer discriminating enough. It should be made harsher and less aligned with implementation internals.

## Reviewer Score

Current score as a local evidence-first case state machine: 8/10.

Current score as a mature LLM-first enterprise approval agent: 5.5/10.

Reason: the architecture is now right, but the model-heavy path has not yet been tested broadly on realistic, messy evidence inputs.

## Recommended Next Phase

Do not add more ledger, connector, or diagnostics features next.

Build:

1. Stage-model shadow benchmark.
2. Realistic evidence attachment set:
   - PDF-like invoice text
   - PO
   - GRN
   - quote
   - budget proof
   - supplier onboarding form
   - sanctions/bank/tax evidence
   - contract exception clauses
3. Comparison report:
   - deterministic baseline
   - model proposal
   - final validator decision
   - whether model found extra risk
   - whether model hallucinated unsupported evidence
   - whether model improved next questions
4. A UI pass that makes evidence chain and rejected evidence impossible to miss.

## Final Recommendation

Proceed to the next phase, but treat it as evaluation hardening, not feature expansion.

The current system is good enough to continue as an evidence-first case agent prototype. It is not yet proven as a mature enterprise approval agent.
